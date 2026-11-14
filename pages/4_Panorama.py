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
    try:
        tabelas["precos"] = tabela(coleta, "precos")
    except Exception:  # coletas antigas, ainda não reclassificadas
        tabelas["precos"] = pd.DataFrame()
    indice_visivel = indice
    st.caption(f"Notas fiscais dos {coleta.get('dias', 10)} dias anteriores a "
               f"{pd.Timestamp(coleta['data_coleta']).strftime('%d/%m/%Y')}.")
    atraso = col.dias_desde_ultima_coleta(indice)
    if atraso is not None and atraso > col.INTERVALO_DIAS + 2:
        st.warning(f"A última coleta foi há **{atraso} dias** (o esperado é a cada {col.INTERVALO_DIAS}). "
                   "A coleta automática pode ter parado: confira a aba Actions do repositório "
                   "(veja docs/COLETA.md, seção \"Como garantir que a coleta não pare\").", icon="⏰")

lojas, municipios, precos = tabelas["lojas"], tabelas["municipios"], tabelas.get("precos", pd.DataFrame())
if "cesta" not in municipios:
    st.error("Esta coleta ainda está no formato antigo. Rode o workflow **reclassificar-coletas** no GitHub.")
    st.stop()

with st.expander("Como a cesta de cada município é calculada"):
    st.markdown(
        """
- **Cesta do município** = soma, para os 12 itens, da quantidade do Decreto-Lei 399 × o **preço mediano
  do item entre as lojas do município**. É a lógica do DIEESE: o pão pode vir da padaria e a carne do
  açougue; não é preciso que uma única loja venda tudo.
- **Cesta econômica**: a mesma conta com o preço baixo de cada item (o 10º percentil das lojas),
  isto é, comprando cada coisa onde ela é barata.
- **Itens estimados**: quando o município não tem nenhuma nota de um item (até 3 itens), o preço dele é
  estimado pela mediana do estado. Esses municípios aparecem marcados; dá para excluí-los abaixo.
"""
    )

c1, c2 = st.columns(2)
max_estimados = c1.select_slider(
    "Itens estimados aceitos por município", options=[0, 1, 2, 3], value=3,
    help="0 = só municípios com os 12 itens encontrados nas próprias notas fiscais.")
minimo_lojas = c2.slider("Mínimo de lojas por item (mediana)", 1, 10, 1,
                         help="Com uma única loja por item, o preço do município depende de um só estabelecimento.")
rank = pan.ranking(municipios, max_estimados, minimo_lojas)

k = st.columns(4)
k[0].metric("Municípios com a cesta", f"{len(rank)} de 102",
            help=f"{int((rank['itens_imputados'] == 0).sum()) if len(rank) else 0} sem nenhum item estimado.")
if not rank.empty:
    k[1].metric("Cesta mediana", brl(rank["cesta"].median()), help="Mediana entre os municípios listados.")
    k[2].metric("Mais barata", brl(rank["cesta"].min()), help=rank.iloc[0]["nome"])
    k[3].metric("Mais cara", brl(rank["cesta"].max()), help=rank.iloc[-1]["nome"])

with st.container(border=True):
    st.markdown("**Análise**")
    for frase in pan.analise_estadual(rank):
        st.markdown(f"- {frase}")

abas = st.tabs(["Mapa", "Ranking", "Preço por item", "Lojas × preço", "Histórico", "Dados e tamanho"])
nomes = {cod: nome_oficial(nome) for nome, cod in MUNICIPIOS_AL.items()}


def legenda_html(legenda: list[tuple[str, str]], titulo: str) -> str:
    return titulo + " " + " ".join(
        f"<span style='display:inline-block;width:12px;height:12px;background:{c};"
        f"border:1px solid #777;margin:0 4px 0 12px;vertical-align:middle'></span>{r}" for c, r in legenda)


with abas[0]:
    geo = malha()
    if geo is None:
        st.info("Não foi possível carregar a malha municipal. O ranking continua disponível.")
    elif rank.empty:
        st.info("Nenhum município atende aos critérios escolhidos.")
    else:
        indicador = st.radio("Indicador", ["Cesta do município", "Cesta econômica"], horizontal=True)
        coluna = "cesta" if indicador == "Cesta do município" else "cesta_economica"
        mapa, legenda = criar_mapa_coropletico(geo, rank, coluna, pan.classes_quantis(rank[coluna]),
                                               col.codigo_da_feicao, nomes, rotulo=indicador)
        html(mapa.get_root().render(), height=520)
        st.markdown(legenda_html(legenda, f"{indicador} (classes por quantis; mais claro = mais caro):"),
                    unsafe_allow_html=True)

with abas[1]:
    if rank.empty:
        st.info("Nenhum município atende aos critérios escolhidos.")
    else:
        st.plotly_chart(graficos.ranking_divergente(rank), use_container_width=True, theme="streamlit")
        st.dataframe(
            rank, hide_index=True, use_container_width=True,
            column_order=["nome", "cesta", "pct_vs_estado", "cesta_economica", "situacao", "itens_sem_preco",
                          "lojas_por_item", "estabelecimentos", "horas_trabalho"],
            column_config={
                "nome": "Município",
                "cesta": st.column_config.NumberColumn("Cesta do município", format="R$ %.2f"),
                "pct_vs_estado": st.column_config.NumberColumn("vs. mediana", format="%+.1f%%"),
                "cesta_economica": st.column_config.NumberColumn("Cesta econômica", format="R$ %.2f"),
                "situacao": "Situação", "itens_sem_preco": "Itens estimados",
                "lojas_por_item": st.column_config.NumberColumn("Lojas por item", format="%.0f"),
                "estabelecimentos": "Lojas no total",
                "horas_trabalho": st.column_config.NumberColumn("Horas de trabalho", format="%.0f h"),
            },
        )

with abas[2]:
    if precos.empty:
        st.info("Esta coleta não tem a tabela de preços por item.")
    else:
        itens_disponiveis = sorted(precos["item"].astype(str).unique())
        item = st.selectbox("Item da cesta", itens_disponiveis)
        do_item = precos[precos["item"].astype(str) == item].copy()
        do_item["nome"] = do_item["municipio"].astype(str).map(nome_oficial)
        do_item["estabelecimentos"] = do_item["lojas"]
        do_item["situacao"] = ""
        unidade = graficos.unidade_legivel(item)
        p1, p2, p3 = st.columns(3)
        p1.metric("Municípios com o item", f"{len(do_item)} de 102")
        p2.metric(f"Preço mediano ({unidade})", brl(do_item["preco_mediano"].median()))
        p3.metric("Do mais barato ao mais caro",
                  f"{brl(do_item['preco_mediano'].min())} a {brl(do_item['preco_mediano'].max())}")
        geo = malha()
        if geo is not None:
            mapa, legenda = criar_mapa_coropletico(geo, do_item, "preco_mediano",
                                                   pan.classes_quantis(do_item["preco_mediano"]),
                                                   col.codigo_da_feicao, nomes, rotulo=f"{item} ({unidade})")
            html(mapa.get_root().render(), height=480)
            st.markdown(legenda_html(legenda, f"{item}, preço mediano em {unidade}:"), unsafe_allow_html=True)
        st.dataframe(
            do_item.sort_values("preco_mediano"), hide_index=True, use_container_width=True,
            column_order=["nome", "preco_mediano", "preco_menor", "lojas"],
            column_config={"nome": "Município", "lojas": "Lojas com o item",
                           "preco_mediano": st.column_config.NumberColumn(f"Preço mediano ({unidade})", format="R$ %.2f"),
                           "preco_menor": st.column_config.NumberColumn("Preço baixo (P10)", format="R$ %.2f")})

with abas[3]:
    if len(rank) < 3:
        st.info("São necessários ao menos 3 municípios para esta análise.")
    else:
        st.plotly_chart(graficos.dispersao_concorrencia(rank), use_container_width=True, theme="streamlit")
        rho = pan.correlacao_spearman(rank["estabelecimentos"], rank["cesta"])
        st.markdown(
            f"**Correlação de Spearman: {pan.descrever_correlacao(rho)}.** Ela mede se, ao ordenar os municípios "
            "pelo número de lojas, a ordem do preço acompanha (vai de −1 a 1; perto de 0 = sem relação). "
            "É uma associação, não prova de causa: municípios maiores têm mais lojas e também outras diferenças."
        )

with abas[4]:
    if len(indice_visivel) < 2:
        st.info("O histórico aparece a partir da segunda coleta (10 dias depois da primeira).")
    st.plotly_chart(graficos.serie_historica(indice_visivel), use_container_width=True, theme="streamlit")

with abas[5]:
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
