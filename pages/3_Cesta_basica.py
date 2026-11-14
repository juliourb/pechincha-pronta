import pandas as pd
import streamlit as st
from streamlit.components.v1 import html

from economiza import cesta_basica as cb
from economiza import graficos
from economiza.api import DIAS_MAXIMO, filtrar_bairro
from economiza.mapa import criar_mapa, para_geojson
from economiza.municipios import codigo_ibge, nome_oficial, normalizar
from economiza.ui import aviso_modo_demo, buscar_cesta_basica, rodape, seletor_municipio

# Streamlit roda este arquivo de cima para baixo A CADA interação do usuário.
# A lógica da cesta está em economiza/cesta_basica.py (sem Streamlit, testável e reutilizável).
st.set_page_config(page_title="Cesta básica · Pechincha Pronta", page_icon="🧺", layout="wide")
st.title("🧺 Cesta básica")
aviso_modo_demo()
st.write(
    "Quanto custa, em cada estabelecimento, a **cesta básica do Decreto-Lei 399/1938** "
    "(Região 2, que inclui Alagoas) — a mesma referência usada pelo DIEESE. **A marca não importa**: "
    "vale o tipo do produto e a presença de **todos os itens** na loja."
)

with st.expander("O que entra na cesta e como o valor é calculado"):
    st.dataframe(
        pd.DataFrame([{"Item": i.nome, "Quantidade mensal": i.quantidade_texto,
                       "Especificação": i.especificacao, "NCM": ", ".join(i.ncms)}
                      for i in cb.ITENS_REGIAO_2]),
        hide_index=True, use_container_width=True,
    )
    st.markdown(
        """
1. Para cada item, o app busca **todas as ofertas** pelo nome do produto (qualquer marca e qualquer
   NCM, porque muitas lojas cadastram o código errado) e mantém só as que batem com a especificação
   (ex.: café **em pó**, não em grão).
2. O preço de cada oferta vira **preço por kg, litro ou dúzia**, lendo o tamanho da embalagem
   na descrição (ex.: arroz 5 kg a R$ 29,90 → R$ 5,98/kg). Banana vendida por kg vira dúzia
   (× 1,2 prata; × 1,8 nanica), como faz o DIEESE.
3. Em cada loja, a **menor cesta** usa a opção mais barata de cada item; a **maior**, a mais cara;
   a **típica**, o preço mediano. Valor = Σ quantidade do decreto × preço.
4. Só têm valor de cesta as lojas que vendem **todos** os itens escolhidos.
5. **Horas de trabalho** = cesta × 220 ÷ salário mínimo (R$ 1.621); **% do salário líquido** =
   cesta ÷ (salário mínimo × 0,925). Fórmulas do DIEESE.

Fontes: DIEESE, *Metodologia da Pesquisa Nacional da Cesta Básica de Alimentos* (ago/2025) e
boletim mensal de out/2026; tabela NCM vigente (Receita Federal).
"""
    )

st.markdown("**1. Onde pesquisar**")
with st.form("consulta_cesta_basica"):
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        cidade = seletor_municipio("cidade_cesta_basica")
    with c2:
        bairro = st.text_input("Bairro (opcional)")
    with c3:
        dias = st.number_input("Últimos dias", 1, DIAS_MAXIMO, 7)
    consultar = st.form_submit_button("Calcular a cesta", type="primary")

if consultar:
    ofertas, falhas = buscar_cesta_basica(codigo_ibge(cidade), int(dias))
    # Guarda o resultado: mudar os itens ou o filtro abaixo NÃO consulta a API de novo.
    if not ofertas.empty:
        ofertas = cb.classificar_ofertas(ofertas)
        ofertas = ofertas[ofertas["motivo"] != "outro produto"]  # resultados da busca que não são o item
    st.session_state["cesta_basica"] = {"ofertas": ofertas,
                                        "falhas": falhas, "cidade": cidade, "bairro": bairro}

if "cesta_basica" not in st.session_state:
    st.info("Escolha o município e clique em **Calcular a cesta**. A consulta faz uma busca por "
            "termo de cada item (16 consultas) e pode levar cerca de um minuto.")
    rodape()
    st.stop()

consulta = st.session_state["cesta_basica"]
if consulta["falhas"]:
    itens_falhos = sorted({f.split(" (")[0] for f in consulta["falhas"]})
    st.warning(f"{len(consulta['falhas'])} consulta(s) à API falharam ({', '.join(itens_falhos)}). "
               "Os itens sem nenhuma resposta aparecem como ausentes.")
    with st.expander("Ver as mensagens da API"):
        st.code("\n".join(consulta["falhas"]), language=None)
ofertas = filtrar_bairro(consulta["ofertas"], consulta["bairro"])
if ofertas.empty or not (ofertas["motivo"] == "ok").any():
    st.error("Nenhuma oferta válida encontrada. Tente outro município, bairro ou período.")
    rodape()
    st.stop()

# ---------------------------------------------------------------- itens que entram e saem
st.markdown("**2. Itens que entram na cesta**")
todos = [i.nome for i in cb.ITENS_REGIAO_2]
c1, c2 = st.columns([3, 1])
itens = c1.multiselect("Itens (retire um item para ver o efeito na cesta)", todos, default=todos)
minimo = c2.slider("Analisar lojas com pelo menos", 1, max(1, len(itens)), max(1, len(itens) // 2),
                   help="Número mínimo de itens para a loja entrar nas análises de cobertura. "
                        "Evita contar padarias e açougues que vendem 1 ou 2 itens.")
if not itens:
    st.info("Selecione ao menos um item.")
    st.stop()
cesta_completa = len(itens) == len(todos)
if not cesta_completa:
    st.caption(f"⚠️ Cesta parcial ({len(itens)} de {len(todos)} itens): os valores não são comparáveis com o DIEESE.")

cestas = cb.cestas_por_estabelecimento(ofertas, itens)
completas = cestas[cestas["completa"]]
comp = cb.composicao(ofertas, cestas, itens)
disp = cb.dispersao_precos(ofertas, itens)
matriz = cb.matriz_cobertura(ofertas, itens, minimo)
sens = cb.sensibilidade(matriz)
referencia = cb.REFERENCIA_DIEESE.get(normalizar(consulta["cidade"])) if cesta_completa and not consulta["bairro"] else None

# ---------------------------------------------------------------- cesta do município
municipal = cb.cesta_municipal(ofertas, itens)
precos_itens = cb.precos_municipio(ofertas, itens)
st.markdown(f"**3. Cesta do município: {nome_oficial(consulta['cidade'])}**"
            + (f" · bairro {consulta['bairro']}" if consulta["bairro"] else ""))
st.caption("Cada item pelo preço mediano entre as lojas que o vendem (o pão pode vir da padaria e a carne do "
           "açougue). É a lógica do DIEESE e não exige que uma única loja tenha tudo.")
cm = st.columns(4)
if pd.notna(municipal["valor"]):
    ref_dieese = cb.REFERENCIA_DIEESE.get(normalizar(consulta["cidade"])) if cesta_completa and not consulta["bairro"] else None
    cm[0].metric("Cesta do município", cb.brl(municipal["valor"]),
                 delta=f"{cb.numero_br(100 * (municipal['valor'] / ref_dieese['valor'] - 1))}% vs. DIEESE" if ref_dieese else None,
                 delta_color="inverse",
                 help=f"DIEESE {ref_dieese['periodo']}: {cb.brl(ref_dieese['valor'])}" if ref_dieese else None)
    cm[1].metric("Cesta econômica", cb.brl(municipal["valor_economico"]),
                 help="Comprando cada item onde ele é barato (10º percentil dos preços entre as lojas).")
    cm[2].metric("Horas de trabalho", cb.formatar_horas(cb.horas_de_trabalho(municipal["valor"])),
                 help=f"{cb.numero_br(cb.percentual_salario_liquido(municipal['valor']))}% do salário mínimo líquido.")
    cm[3].metric("Lojas por item (mediana)", f"{municipal['lojas_por_item_mediana']:.0f}")
else:
    cm[0].metric("Itens com preço", f"{municipal['itens_com_preco']} de {len(itens)}")
    st.info(f"Sem notas fiscais no período para: **{municipal['itens_faltando']}**. Retire esses itens acima "
            "para calcular a cesta com os demais.")

# ---------------------------------------------------------------- indicadores
st.markdown("**4. Cesta numa única loja** (estabelecimentos que vendem todos os itens)")
m = st.columns(5)
m[0].metric("Cestas completas", f"{len(completas)} de {int((cestas['n_itens'] >= minimo).sum())}",
            help=f"Lojas com todos os itens, entre as que vendem pelo menos {minimo} itens.")
if completas.empty:
    st.info("Nenhum estabelecimento vende todos os itens escolhidos. Veja a aba **Entram e saem** "
            "para descobrir qual item mais limita, ou retire itens acima.")
else:
    mediana = completas["cesta_min"].median()
    m[1].metric("Menor cesta", cb.brl(completas["cesta_min"].min()))
    m[2].metric("Mediana", cb.brl(mediana),
                delta=f"{cb.numero_br(100 * (mediana / referencia['valor'] - 1))}% vs. DIEESE" if referencia else None,
                delta_color="inverse",
                help=f"DIEESE {referencia['periodo']}: {cb.brl(referencia['valor'])}" if referencia else None)
    m[3].metric("Maior cesta", cb.brl(completas["cesta_min"].max()))
    m[4].metric("Horas de trabalho", cb.formatar_horas(cb.horas_de_trabalho(mediana)),
                help=f"Para comprar a cesta mediana com um salário mínimo. Equivale a "
                     f"{cb.numero_br(cb.percentual_salario_liquido(mediana))}% do salário mínimo líquido.")

    with st.container(border=True):
        st.markdown("**Análise**")
        for frase in cb.analise_textual(cestas, comp, disp, sens, minimo, len(itens), referencia):
            st.markdown(f"- {frase}")

moeda = {"format": "R$ %.2f"}
abas = st.tabs(["Distribuição", "Por estabelecimento", "Itens", "Entram e saem", "Mapa", "Diagnóstico",
                "Preços no município"])

with abas[6]:
    st.caption("Base da cesta do município: preço de cada item entre as lojas (opção mais barata de cada loja).")
    tabela_precos = precos_itens.assign(
        quantidade=precos_itens["item"].map(lambda n: cb.ITENS_POR_NOME[n].quantidade_texto),
        gasto=precos_itens["preco_mediano"] * precos_itens["item"].map(lambda n: cb.ITENS_POR_NOME[n].quantidade))
    st.dataframe(
        tabela_precos.sort_values("gasto", ascending=False), hide_index=True, use_container_width=True,
        column_order=["item", "quantidade", "lojas", "preco_mediano", "preco_menor", "gasto"],
        column_config={"item": "Item", "quantidade": "Quantidade mensal", "lojas": "Lojas com o item",
                       "preco_mediano": st.column_config.NumberColumn("Preço mediano (kg/L/dz)", **moeda),
                       "preco_menor": st.column_config.NumberColumn("Preço baixo (P10)", **moeda),
                       "gasto": st.column_config.NumberColumn("Gasto na cesta", **moeda)})

with abas[0]:
    if completas.empty:
        st.info("Sem lojas com a cesta completa.")
    else:
        st.plotly_chart(graficos.distribuicao_cestas(cestas, referencia), use_container_width=True, theme="streamlit")

with abas[1]:
    if not completas.empty:
        st.plotly_chart(graficos.faixa_por_estabelecimento(cestas), use_container_width=True, theme="streamlit")
    st.markdown("**Lojas com a cesta completa**")
    st.dataframe(
        completas, hide_index=True, use_container_width=True,
        column_order=["estabelecimento", "cesta_min", "cesta_tipica", "cesta_max", "amplitude",
                      "bairro", "logradouro", "numero"],
        column_config={
            "estabelecimento": "Estabelecimento", "bairro": "Bairro", "logradouro": "Endereço", "numero": "Nº",
            "cesta_min": st.column_config.NumberColumn("Menor cesta", **moeda),
            "cesta_tipica": st.column_config.NumberColumn("Típica", **moeda),
            "cesta_max": st.column_config.NumberColumn("Maior cesta", **moeda),
            "amplitude": st.column_config.NumberColumn("Maior − menor", **moeda),
        },
    )
    incompletas = cestas[~cestas["completa"] & (cestas["n_itens"] >= minimo)]
    if not incompletas.empty:
        st.markdown(f"**Lojas sem a cesta completa** (com pelo menos {minimo} itens)")
        st.dataframe(
            incompletas, hide_index=True, use_container_width=True,
            column_order=["estabelecimento", "n_itens", "itens_faltando", "bairro"],
            column_config={
                "estabelecimento": "Estabelecimento", "bairro": "Bairro", "itens_faltando": "Falta",
                "n_itens": st.column_config.ProgressColumn("Itens que tem", min_value=0, max_value=len(itens), format="%d"),
            },
        )

with abas[2]:
    if not comp.empty:
        st.plotly_chart(graficos.composicao_barras(comp), use_container_width=True, theme="streamlit")
    if not disp.empty:
        st.plotly_chart(graficos.dispersao_barras(disp), use_container_width=True, theme="streamlit")
        st.dataframe(
            disp, hide_index=True, use_container_width=True,
            column_config={"item": "Item", "unidade": "Unidade", "estabelecimentos": "Lojas",
                           "menor": st.column_config.NumberColumn("Menor preço", **moeda),
                           "mediano": st.column_config.NumberColumn("Mediano", **moeda),
                           "maior": st.column_config.NumberColumn("Maior", **moeda),
                           "razao_maior_menor": st.column_config.NumberColumn("Maior ÷ menor", format="%.2f×")},
        )

with abas[3]:
    if matriz.empty:
        st.info("Nenhuma loja com o mínimo de itens escolhido.")
    else:
        st.plotly_chart(graficos.sensibilidade_barras(sens), use_container_width=True, theme="streamlit")
        quase = cestas[(cestas["n_itens"] == len(itens) - 1)]
        if not quase.empty:
            st.markdown(f"**Quase completas** — {len(quase)} loja(s) com só 1 item faltando:")
            st.dataframe(quase[["estabelecimento", "itens_faltando", "bairro"]], hide_index=True,
                         use_container_width=True,
                         column_config={"estabelecimento": "Estabelecimento", "itens_faltando": "Falta", "bairro": "Bairro"})
        st.plotly_chart(graficos.mapa_cobertura(matriz), use_container_width=True, theme="streamlit")

with abas[4]:
    mapa = criar_mapa(completas, "cesta_min")
    if mapa is None:
        st.info("Nenhuma loja com a cesta completa e coordenadas para mostrar no mapa.")
    else:
        st.caption("🔴 menor cesta · 🔵 demais lojas com a cesta completa")
        html(mapa.get_root().render(), height=560)

with abas[5]:
    st.caption("Como cada oferta da API foi tratada. Use para conferir se o filtro de especificação "
               "e a leitura do tamanho da embalagem estão corretos.")
    st.dataframe(cb.resumo_diagnostico(ofertas), hide_index=True, use_container_width=True)
    filtro = st.selectbox("Ver ofertas", ["descartadas", "aceitas", "todas"])
    vis = {"descartadas": ofertas[ofertas["motivo"] != "ok"], "aceitas": ofertas[ofertas["motivo"] == "ok"],
           "todas": ofertas}[filtro]
    st.dataframe(vis[["item", "motivo", "descricao", "unidade_medida", "valor_declarado", "preco_base", "estabelecimento"]],
                 hide_index=True, use_container_width=True,
                 column_config={"preco_base": st.column_config.NumberColumn("Preço por kg/L/dz", **moeda),
                                "valor_declarado": st.column_config.NumberColumn("Preço na nota", **moeda)})

d1, d2, d3 = st.columns(3)
d1.download_button("Cestas por loja (CSV)", cestas.to_csv(index=False).encode("utf-8"), "cesta_basica_lojas.csv", "text/csv")
d2.download_button("Lojas completas (GeoJSON)", para_geojson(completas, list(completas.columns)),
                   "cesta_basica.geojson", "application/geo+json")
d3.download_button("Ofertas classificadas (CSV)", ofertas.to_csv(index=False).encode("utf-8"), "cesta_basica_ofertas.csv", "text/csv")

rodape()
