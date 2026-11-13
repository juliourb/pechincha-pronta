import os
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.components.v1 import html

from economiza import coleta as col
from economiza import graficos
from economiza import panorama as pan
from economiza.cesta_basica import brl, numero_br
from economiza.demo import DemoClient
from economiza.mapa import criar_mapa_coropletico
from economiza.municipios import MUNICIPIOS_AL, NOMES_MUNICIPIOS, nome_oficial

st.set_page_config(page_title="Panorama de Alagoas · Pechincha Pronta", page_icon="🗺️", layout="wide")
st.title("🗺️ Panorama de Alagoas")
st.write(
    "A cesta básica (Decreto-Lei 399/1938) nos **102 municípios**, a partir de coletas automáticas feitas "
    "**a cada 10 dias** (notas fiscais dos 10 dias anteriores). Os dados ficam guardados, então esta página "
    "abre na hora, sem consultar a API."
)

# Pasta local com coletas (desenvolvimento e testes); senão, lê as Releases públicas do GitHub.
PASTA = Path(os.environ["PECHINCHA_COLETAS_DIR"]) if os.environ.get("PECHINCHA_COLETAS_DIR") else None


@st.cache_data(ttl=6 * 3600, show_spinner="Carregando o índice das coletas…")
def indice_publicado() -> list[dict]:
    try:
        return col.ler_indice(PASTA)
    except Exception:
        return []


@st.cache_data(ttl=6 * 3600, show_spinner="Baixando a coleta…")
def tabela(coleta: dict, nome: str) -> pd.DataFrame:
    return col.ler_tabela(coleta, nome, PASTA)


@st.cache_data(show_spinner="Gerando dados de demonstração…")
def coleta_demo() -> tuple[dict, dict[str, pd.DataFrame]]:
    ofertas, _, _ = col.coletar(DemoClient(), NOMES_MUNICIPIOS, dias=10)
    tabelas = col.montar_tabelas(ofertas, col.hoje())
    return {"tag": "demo", "data_coleta": col.hoje(), "dias": 10, "estado": col.resumo_estadual(tabelas)}, tabelas


@st.cache_data(ttl=24 * 3600, show_spinner="Baixando a malha municipal…")
def malha() -> dict | None:
    return col.carregar_malha()


indice = indice_publicado()
demo = not indice
if demo:
    st.warning(
        "**Ainda não há coletas publicadas** (ou não foi possível acessá-las). Abaixo, uma **prévia com dados "
        "fictícios** do modo demonstração. A primeira coleta real é feita pelo GitHub Actions (veja o README).",
        icon="🧪",
    )
    coleta, tabelas = coleta_demo()
    indice_visivel = [coleta]
else:
    datas = [c["data_coleta"] for c in indice][::-1]
    escolha = st.selectbox("Coleta", datas, format_func=lambda d: pd.Timestamp(d).strftime("%d/%m/%Y"))
    coleta = next(c for c in indice if c["data_coleta"] == escolha)
    tabelas = {nome: tabela(coleta, nome) for nome in ("lojas", "municipios")}
    indice_visivel = indice
    st.caption(f"Notas fiscais dos {coleta.get('dias', 10)} dias anteriores a "
               f"{pd.Timestamp(coleta['data_coleta']).strftime('%d/%m/%Y')}.")

lojas, municipios = tabelas["lojas"], tabelas["municipios"]
minimo = st.slider("Considerar municípios com pelo menos N lojas com a cesta completa", 1, 10, 3,
                   help="Com poucas lojas, a mediana de um município fica instável. 3 é um bom ponto de partida.")
rank = pan.ranking(municipios, minimo)

e = coleta["estado"]
k = st.columns(4)
k[0].metric("Municípios analisados", f"{len(rank)} de 102")
k[1].metric("Lojas com a cesta completa", f"{e['lojas_com_cesta']:,}".replace(",", "."))
k[2].metric("Mediana estadual", brl(e["cesta_mediana"]) if e["cesta_mediana"] else "—")
if not rank.empty:
    k[3].metric("Diferença entre municípios", brl(rank["mediana"].max() - rank["mediana"].min()),
                help="Entre a maior e a menor cesta mediana municipal.")

with st.container(border=True):
    st.markdown("**Análise**")
    for frase in pan.analise_estadual(rank, lojas, minimo):
        st.markdown(f"- {frase}")

abas = st.tabs(["Mapa", "Ranking", "Lojas × preço", "Histórico", "Dados e tamanho"])

with abas[0]:
    geo = malha()
    if geo is None:
        st.info("Não foi possível baixar a malha municipal do IBGE agora. O ranking continua disponível.")
    elif rank.empty:
        st.info("Nenhum município atende ao mínimo de lojas escolhido.")
    else:
        nomes = {cod: nome_oficial(nome) for nome, cod in MUNICIPIOS_AL.items()}
        limites = pan.classes_quantis(rank["mediana"])
        mapa, legenda = criar_mapa_coropletico(geo, rank, "mediana", limites, col.codigo_da_feicao, nomes)
        html(mapa.get_root().render(), height=520)
        st.markdown(
            "Cesta mediana por município (classes por quantis): " + " ".join(
                f"<span style='display:inline-block;width:12px;height:12px;background:{c};"
                f"border:1px solid #999;margin:0 4px 0 12px;vertical-align:middle'></span>{r}"
                for c, r in legenda),
            unsafe_allow_html=True)

with abas[1]:
    if rank.empty:
        st.info("Nenhum município atende ao mínimo de lojas escolhido.")
    else:
        st.plotly_chart(graficos.ranking_divergente(rank), use_container_width=True, theme="streamlit")
        st.dataframe(
            rank, hide_index=True, use_container_width=True,
            column_order=["nome", "mediana", "pct_vs_estado", "menor_cesta", "maior_cesta", "com_cesta_completa",
                          "estabelecimentos", "horas_trabalho_mediana"],
            column_config={
                "nome": "Município",
                "mediana": st.column_config.NumberColumn("Mediana", format="R$ %.2f"),
                "pct_vs_estado": st.column_config.NumberColumn("vs. estado", format="%+.1f%%"),
                "menor_cesta": st.column_config.NumberColumn("Menor", format="R$ %.2f"),
                "maior_cesta": st.column_config.NumberColumn("Maior", format="R$ %.2f"),
                "com_cesta_completa": "Lojas com a cesta",
                "estabelecimentos": "Lojas com algum item",
                "horas_trabalho_mediana": st.column_config.NumberColumn("Horas de trabalho", format="%.0f h"),
            },
        )

with abas[2]:
    if len(rank) < 3:
        st.info("São necessários ao menos 3 municípios para esta análise.")
    else:
        st.plotly_chart(graficos.dispersao_concorrencia(rank), use_container_width=True, theme="streamlit")
        rho = pan.correlacao_spearman(rank["com_cesta_completa"], rank["mediana"])
        st.markdown(
            f"**Correlação de Spearman: {pan.descrever_correlacao(rho)}.** Ela mede se, ao ordenar os municípios "
            "pelo número de lojas, a ordem do preço acompanha (vai de −1 a 1; perto de 0 = sem relação). "
            "É uma associação, não prova de causa: municípios maiores têm mais lojas e também outras diferenças."
        )

with abas[3]:
    if len(indice_visivel) < 2:
        st.info("O histórico aparece a partir da segunda coleta (10 dias depois da primeira).")
    st.plotly_chart(graficos.serie_historica(indice_visivel), use_container_width=True, theme="streamlit")

with abas[4]:
    if demo:
        st.info("Os tamanhos reais aparecem depois da primeira coleta publicada.")
    else:
        if coleta.get("demo"):
            st.warning("Esta coleta foi feita em modo demonstração: os tamanhos não representam dados reais.")
        tam = col.tamanho_das_coletas(indice)
        proj = col.projecao_anual(indice)
        t = st.columns(3)
        t[0].metric("Coletas guardadas", proj["coletas"])
        t[1].metric("Tamanho médio por coleta", f"{numero_br(proj['mb_por_coleta'], 1)} MB")
        t[2].metric("Projeção por ano", f"{numero_br(proj['mb_por_ano'], 0)} MB",
                    help=f"Média por coleta × {numero_br(col.COLETAS_POR_ANO, 1)} coletas por ano.")
        tabela_tam = tam.pivot_table(index="data_coleta", columns="arquivo", values=["linhas", "mb"], aggfunc="sum")
        tabela_tam.columns = [f"{arq} ({'linhas' if med == 'linhas' else 'MB'})" for med, arq in tabela_tam.columns]
        st.dataframe(tabela_tam.rename_axis("Coleta").style.format(
            {c: "{:,.0f}" if "linhas" in c else "{:.2f}" for c in tabela_tam.columns}), use_container_width=True)
        st.markdown("**Baixar esta coleta (Parquet):** " + " · ".join(
            f"[{n}]({col.url_download(coleta, n)})" for n in col.ARQUIVOS))
        st.markdown("Para analisar em SQL, sem baixar tudo para a memória, use o [DuckDB](https://duckdb.org):")
        st.code(
            "SELECT municipio, item, median(preco_base) AS preco_mediano\n"
            f"FROM '{col.url_download(coleta, 'ofertas')}'\n"
            "WHERE motivo = 'ok'\nGROUP BY ALL ORDER BY municipio, item;", language="sql")

st.divider()
st.caption("Dados: API pública Economiza Alagoas (SEFAZ-AL). Metodologia: docs/CESTA_BASICA.md. "
           "Malha municipal: IBGE.")
