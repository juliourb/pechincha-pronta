import streamlit as st
from streamlit.components.v1 import html

from economiza.api import DIAS_MAXIMO, EconomizaAPIError, filtrar_bairro
import pandas as pd

from economiza.cesta import (CESTA_CHURRASCO, classificar_churrasco, filtrar_ofertas, montar_carrinho,
                             resumo_por_item, total_por_estabelecimento)
from economiza.cesta_basica import brl, resumo_diagnostico
from economiza.mapa import criar_mapa, para_geojson
from economiza.municipios import codigo_ibge
from economiza.ui import (aviso_modo_demo, buscar_cesta, buscar_por_gtin, rodape, seletor_municipio,
                          seletor_produtos)

MAX_GTIN_POR_ITEM = 5  # limite de consultas extras por código de barras

# Streamlit roda este arquivo de cima para baixo A CADA interação do usuário.
# Guia didático com os conceitos usados aqui: docs/GUIA_STREAMLIT.md
st.set_page_config(page_title="Churrasco · Pechincha Pronta", page_icon="🍖", layout="wide")
st.title("🍖 Cesta de churrasco")
aviso_modo_demo()
st.caption("Os preços são comparados **por kg ou por litro**: assim uma lata avulsa, um pacote com 12 "
           "e uma garrafa de 600 ml entram na mesma régua.")

st.markdown("**1. Escolha o município e os itens da cesta**")
with st.form("consulta_cesta"):
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        cidade = seletor_municipio("cidade_churrasco")
    with c2:
        bairro = st.text_input("Bairro (opcional)")
    with c3:
        dias = st.number_input("Últimos dias", 1, DIAS_MAXIMO, 7)
    itens = st.multiselect("Itens", list(CESTA_CHURRASCO), default=["Picanha", "Carvão", "Cerveja"])
    consultar = st.form_submit_button("Consultar preços", type="primary")

if consultar:
    if not itens:
        st.warning("Selecione ao menos um item.")
    else:
        try:
            df = buscar_cesta(itens, codigo_ibge(cidade), int(dias))
            # Guarda os dados da API na "memória" da sessão: ao mudar quantidades e filtros
            # abaixo, o script roda de novo, mas reaproveita estes dados sem nova consulta.
            st.session_state["cesta"] = {"ofertas": classificar_churrasco(df), "itens": itens,
                                         "cidade": cidade, "bairro": bairro, "dias": int(dias)}
        except EconomizaAPIError as erro:
            st.error(f"Não foi possível consultar a API. {erro}")
            st.session_state.pop("cesta", None)

# Ainda não houve consulta: mostra uma dica e para a execução aqui (st.stop).
if "cesta" not in st.session_state:
    st.info("Escolha os itens e clique em **Consultar preços**.")
    rodape()
    st.stop()

consulta = st.session_state["cesta"]
ofertas = filtrar_bairro(consulta["ofertas"], consulta["bairro"])
encontrados = set(ofertas.loc[ofertas["motivo"] == "ok", "item"]) if not ofertas.empty else set()
faltando = [i for i in consulta["itens"] if i not in encontrados]
if faltando:
    st.warning(f"Sem ofertas válidas para: **{', '.join(faltando)}**. Esses itens ficaram fora da cesta.")
itens = [i for i in consulta["itens"] if i in encontrados]
if not itens:
    st.info("Nenhum item encontrado. Tente outro município, bairro ou período.")
    rodape()
    st.stop()

# ---------------------------------------------------------------- quantidades e subfiltros
st.markdown("**2. Quantidade e filtros de cada item**")
st.caption("**Tipo** restringe o formato (lata, long neck, carne congelada…). **Marca** filtra pelo nome "
           "(ex.: `skol`) e reduz a lista de **Produtos**, onde dá para marcar itens específicos. "
           "Em branco, vale a opção mais barata.")
quantidades, filtros = {}, {}
for item in itens:
    definicao = CESTA_CHURRASCO[item]
    with st.container(border=True):
        c_q, c_s = st.columns([1, 1])
        quantidades[item] = c_q.number_input(
            f"**{item}** — quantidade ({definicao.unidade})", min_value=0.1, step=0.5,
            value=float(definicao.quantidade_padrao), key=f"q_{item}", help=f"Em {definicao.dica}.")
        opcoes = ["Qualquer", *definicao.subfiltros]
        tipo = c_s.selectbox("Tipo", opcoes, key=f"s_{item}", disabled=len(opcoes) == 1)
        subfiltro = None if tipo == "Qualquer" else tipo
        # Filtro de produtos comum a todas as páginas (economiza/ui.py + economiza/produtos.py):
        # marca + lista do que foi encontrado, já restrita ao "Tipo" escolhido.
        do_tipo = filtrar_ofertas(ofertas, {item: {"subfiltro": subfiltro}})
        filtros[item] = {"subfiltro": subfiltro,
                         **seletor_produtos(do_tipo, item, definicao.unidade, f"{item}_{tipo}")}

# Busca extra pelo código de barras: acha o produto escolhido mesmo nas lojas que o
# descrevem de outro jeito na nota (ex.: "HNK LN 330" em vez de "CERVEJA HEINEKEN").
escolhidos = {i: [p[5:] for p in f["produtos"] if p.startswith("gtin:")][:MAX_GTIN_POR_ITEM]
              for i, f in filtros.items()}
if any(escolhidos.values()):
    if st.checkbox("Procurar os produtos escolhidos também pelo código de barras",
                   help="Faz uma consulta extra à API por produto. Encontra lojas que descrevem o mesmo "
                        "produto de outra forma na nota fiscal."):
        extras = []
        with st.spinner("Consultando pelo código de barras…"):
            for item, gtins in escolhidos.items():
                for gtin in gtins:
                    try:
                        df = buscar_por_gtin(codigo_ibge(consulta["cidade"]), gtin, consulta.get("dias", 7))
                    except EconomizaAPIError:
                        continue
                    if not df.empty:
                        extras.append(classificar_churrasco(df.assign(item=item), pelo_codigo_de_barras=True))
        if extras:
            antes = ofertas["cnpj"].nunique()
            ofertas = pd.concat([ofertas, filtrar_bairro(pd.concat(extras, ignore_index=True), consulta["bairro"])],
                                ignore_index=True).drop_duplicates(["cnpj", "item", "produto", "data_venda"])
            st.caption(f"Busca por código de barras: {ofertas['cnpj'].nunique() - antes} loja(s) a mais.")

# Cálculo refeito a cada mudança nos campos acima; é rápido porque usa só pandas,
# sem chamar a API. As regras estão em economiza/cesta.py.
filtradas = filtrar_ofertas(ofertas, filtros)
resumo = resumo_por_item(filtradas).set_index("item")
for item in itens:
    if item not in resumo.index:
        st.error(f"Nenhuma oferta de **{item}** passa nos filtros escolhidos. Afrouxe o tipo, a marca ou os produtos.")
carrinho = montar_carrinho(filtradas, quantidades)
totais = total_por_estabelecimento(carrinho, ofertas)

st.markdown("**3. Onde tem uma Pechincha Pronta?**")
if totais.empty:
    st.info("Nenhum estabelecimento vende **todos** os itens com esses filtros. "
            "Tente remover um item ou afrouxar um filtro.")
    rodape()
    st.stop()

melhor = totais.iloc[0]
m1, m2, m3 = st.columns(3)
m1.metric("Lojas com a cesta completa", len(totais))
m2.metric("Menor total", brl(melhor["valor_cesta"]), help=melhor["estabelecimento"])
if len(totais) > 1:
    m3.metric("Economia vs. mais caro", brl(totais["valor_cesta"].max() - melhor["valor_cesta"]))
st.success(f"Melhor opção: **{melhor['estabelecimento']}**, {brl(melhor['valor_cesta'])}")

moeda = {"format": "R$ %.2f"}
aba_total, aba_itens, aba_mapa, aba_diag = st.tabs(["Total por estabelecimento", "Por item", "Mapa", "Diagnóstico"])
with aba_total:
    st.dataframe(
        totais, hide_index=True, use_container_width=True,
        column_order=["estabelecimento", "valor_cesta", "ultima_nota", "bairro", "logradouro", "numero"],
        column_config={"estabelecimento": "Estabelecimento", "bairro": "Bairro",
                       "logradouro": "Endereço", "numero": "Nº",
                       "valor_cesta": st.column_config.NumberColumn("Total da cesta", **moeda),
                       "ultima_nota": st.column_config.DatetimeColumn("Nota mais recente", format="DD/MM/YYYY HH:mm")},
    )
with aba_itens:
    st.caption("Produto escolhido em cada loja: o mais barato por kg/litro entre os que passam nos filtros. "
               "O subtotal é proporcional; na prática você compra embalagens inteiras.")
    st.dataframe(
        carrinho, hide_index=True, use_container_width=True,
        column_order=["estabelecimento", "item", "descricao", "valor_declarado", "preco_base", "unidade",
                      "quantidade", "valor_item", "data_venda"],
        column_config={"estabelecimento": "Estabelecimento", "item": "Item", "descricao": "Produto",
                       "valor_declarado": st.column_config.NumberColumn("Preço na nota", **moeda),
                       "preco_base": st.column_config.NumberColumn("Preço por kg/L", **moeda),
                       "unidade": "Un.", "quantidade": "Qtd.",
                       "valor_item": st.column_config.NumberColumn("Subtotal", **moeda),
                       "data_venda": st.column_config.DatetimeColumn("Nota", format="DD/MM/YYYY HH:mm")},
    )
with aba_mapa:
    mapa = criar_mapa(totais, "valor_cesta")
    if mapa is None:
        st.info("Nenhum estabelecimento com coordenadas para mostrar no mapa.")
    else:
        st.caption("🔴 menor total · 🔵 demais estabelecimentos")
        # O mapa é feito com folium (Leaflet) e inserido na página como HTML.
        html(mapa.get_root().render(), height=560)
with aba_diag:
    st.caption("Como cada oferta foi tratada: descartada quando não é o item (ex.: picanha suína) "
               "ou quando a descrição não informa o tamanho da embalagem.")
    st.dataframe(resumo_diagnostico(ofertas), hide_index=True, use_container_width=True)
    st.dataframe(ofertas[ofertas["motivo"] != "ok"][["item", "motivo", "descricao", "unidade_medida",
                                                     "valor_declarado", "estabelecimento"]],
                 hide_index=True, use_container_width=True)

d1, d2 = st.columns(2)
d1.download_button("Baixar CSV", totais.to_csv(index=False).encode("utf-8"), "cesta_churrasco.csv", "text/csv")
d2.download_button("Baixar GeoJSON (QGIS)", para_geojson(totais, list(totais.columns)),
                   "cesta_churrasco.geojson", "application/geo+json")

rodape()
