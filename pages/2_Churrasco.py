import streamlit as st
from streamlit.components.v1 import html

from economiza.api import DIAS_MAXIMO, EconomizaAPIError, filtrar_bairro
from economiza.cesta import CESTA_CHURRASCO, montar_carrinho, opcoes_por_item, total_por_estabelecimento
from economiza.mapa import criar_mapa, para_geojson
from economiza.municipios import codigo_ibge
from economiza.ui import aviso_modo_demo, buscar_cesta, rodape, seletor_municipio

# Streamlit roda este arquivo de cima para baixo A CADA interação do usuário.
# Guia didático com os conceitos usados aqui: docs/GUIA_STREAMLIT.md
st.set_page_config(page_title="Churrasco · Pechincha Pronta", page_icon="🍖", layout="wide")
st.title("🍖 Cesta de churrasco")
aviso_modo_demo()

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
            # Guarda os dados da API na "memória" da sessão: ao mudar quantidades ou marcas
            # abaixo, o script roda de novo, mas reaproveita estes dados sem nova consulta.
            st.session_state["cesta"] = {"df": df, "itens": itens, "cidade": cidade, "bairro": bairro}
        except EconomizaAPIError as erro:
            st.error(f"Não foi possível consultar a API. {erro}")
            st.session_state.pop("cesta", None)

# Ainda não houve consulta: mostra uma dica e para a execução aqui (st.stop).
if "cesta" not in st.session_state:
    st.info("Escolha os itens e clique em **Consultar preços**.")
    rodape()
    st.stop()

consulta = st.session_state["cesta"]
df = filtrar_bairro(consulta["df"], consulta["bairro"])
itens = consulta["itens"]
encontrados = opcoes_por_item(df)
faltando = [i for i in itens if i not in encontrados]
if faltando:
    st.warning(f"Sem notas fiscais para: **{', '.join(faltando)}**. Esses itens ficaram fora da cesta.")
itens = [i for i in itens if i in encontrados]
if not itens:
    st.info("Nenhum item encontrado. Tente outro município, bairro ou período.")
    rodape()
    st.stop()

st.markdown("**2. Ajuste quantidades e, se quiser, a descrição exata de cada item**")
st.caption("A quantidade multiplica o preço da unidade de venda (kg, lata, pacote…). "
           "Deixe a descrição em branco para usar a opção mais barata de cada loja.")
quantidades, escolhas = {}, {}
for item in itens:
    q, e = st.columns([1, 3])
    quantidades[item] = q.number_input(f"Qtd. {item}", min_value=0.1, value=1.0, step=0.5, key=f"q_{item}")
    escolhas[item] = e.selectbox(f"Descrição de {item}", [None, *encontrados[item]], key=f"e_{item}",
                                 format_func=lambda v: "— mais barato —" if v is None else v)

# Cálculo refeito a cada mudança nos campos acima; é rápido porque usa só pandas,
# sem chamar a API. A regra da cesta está em economiza/cesta.py.
carrinho = montar_carrinho(df, quantidades, escolhas)
totais = total_por_estabelecimento(carrinho, df)

st.markdown("**3. Onde tem uma Pechincha Pronta?**")
if totais.empty:
    st.info("Nenhum estabelecimento vende **todos** os itens escolhidos. "
            "Tente remover um item ou deixar a descrição em branco.")
    rodape()
    st.stop()

melhor = totais.iloc[0]
m1, m2, m3 = st.columns(3)
m1.metric("Estabelecimentos com a cesta completa", len(totais))
m2.metric("Menor total", f"R$ {melhor['valor_cesta']:.2f}", help=melhor["estabelecimento"])
if len(totais) > 1:
    m3.metric("Economia vs. mais caro", f"R$ {totais['valor_cesta'].max() - melhor['valor_cesta']:.2f}")
st.success(f"Melhor opção: **{melhor['estabelecimento']}** — R$ {melhor['valor_cesta']:.2f}")

moeda = {"format": "R$ %.2f"}
aba_total, aba_itens, aba_mapa = st.tabs(["Total por estabelecimento", "Por item", "Mapa"])
with aba_total:
    st.dataframe(
        totais, hide_index=True, use_container_width=True,
        column_order=["estabelecimento", "valor_cesta", "ultima_nota", "bairro", "logradouro", "numero", "telefone"],
        column_config={"estabelecimento": "Estabelecimento", "bairro": "Bairro",
                       "logradouro": "Endereço", "numero": "Nº", "telefone": "Telefone",
                       "valor_cesta": st.column_config.NumberColumn("Total da cesta", **moeda),
                       "ultima_nota": st.column_config.DatetimeColumn("Nota mais recente", format="DD/MM/YYYY HH:mm")},
    )
with aba_itens:
    st.dataframe(
        carrinho, hide_index=True, use_container_width=True,
        column_order=["estabelecimento", "item", "descricao", "valor_venda", "quantidade", "valor_item", "data_venda"],
        column_config={"estabelecimento": "Estabelecimento", "item": "Item", "descricao": "Descrição",
                       "quantidade": "Qtd.",
                       "valor_venda": st.column_config.NumberColumn("Preço unitário", **moeda),
                       "valor_item": st.column_config.NumberColumn("Subtotal", **moeda),
                       "data_venda": st.column_config.DatetimeColumn("Nota", format="DD/MM/YYYY HH:mm")},
    )
with aba_mapa:
    mapa = criar_mapa(totais, "valor_cesta")
    if mapa is None:
        st.info("Nenhum estabelecimento com coordenadas para mostrar no mapa.")
    else:
        st.caption("🔴 menor total · 🔵 demais estabelecimentos")
        html(mapa.get_root().render(), height=560)

d1, d2 = st.columns(2)
d1.download_button("Baixar CSV", totais.to_csv(index=False).encode("utf-8"), "cesta_churrasco.csv", "text/csv")
d2.download_button("Baixar GeoJSON (QGIS)", para_geojson(totais, list(totais.columns)),
                   "cesta_churrasco.geojson", "application/geo+json")

rodape()
