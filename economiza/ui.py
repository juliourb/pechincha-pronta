"""Componentes de interface compartilhados entre as páginas do Streamlit."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import obter_cliente
from .api import EconomizaAPIError
from .cesta import CESTA_CHURRASCO
from .cesta_basica import consultas_api, remover_duplicadas
from .municipios import NOMES_MUNICIPIOS, nome_oficial

CACHE_TTL = 15 * 60  # 15 min: os preços vêm de notas fiscais, não mudam a cada segundo


def em_modo_demo() -> bool:
    return getattr(obter_cliente(), "demo", False)


def aviso_modo_demo() -> None:
    if em_modo_demo():
        st.warning(
            "**Modo demonstração:** nenhum token da API foi configurado, então os preços, "
            "nomes e posições exibidos são **fictícios**. Veja no README como configurar "
            "o token `ECONOMIZA_AL_TOKEN`.",
            icon="🧪",
        )


def seletor_municipio(key: str) -> str:
    padrao = NOMES_MUNICIPIOS.index("MACEIO")
    return st.selectbox("Município", NOMES_MUNICIPIOS, index=padrao, key=key,
                        format_func=nome_oficial)


# @st.cache_data guarda o resultado da função: chamadas com os mesmos argumentos
# (mesmo combustível, município e período) não consultam a API de novo durante o TTL.
# O cache é compartilhado entre todos os usuários do app.
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def buscar_combustivel(tipo: int, codigo_ibge: int, dias: int) -> pd.DataFrame:
    return obter_cliente().pesquisar_combustivel(tipo, codigo_ibge, dias)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _buscar_produto(codigo_ibge: int, descricao: str, ncm: str, dias: int) -> pd.DataFrame:
    return obter_cliente().pesquisar_produto(codigo_ibge, descricao=descricao, ncm=ncm, dias=dias)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def buscar_por_gtin(codigo_ibge: int, gtin: str, dias: int) -> pd.DataFrame:
    """Todas as lojas do município que venderam o produto com este código de barras."""
    return obter_cliente().pesquisar_produto(codigo_ibge, gtin=gtin, dias=dias)


def buscar_cesta(itens: list[str], codigo_ibge: int, dias: int) -> pd.DataFrame:
    """Uma consulta por (item, NCM); cada linha recebe a coluna ``item``."""
    partes = []
    progresso = st.progress(0.0, text="Consultando a API…")
    consultas = [(item, ncm) for item in itens for ncm in CESTA_CHURRASCO[item].ncms]
    for n, (item, ncm) in enumerate(consultas, start=1):
        df = _buscar_produto(codigo_ibge, CESTA_CHURRASCO[item].descricao_api, ncm, dias)
        if not df.empty:
            partes.append(df.assign(item=item))
        progresso.progress(n / len(consultas), text=f"Consultando {item} (NCM {ncm})…")
    progresso.empty()
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _buscar_termo(codigo_ibge: int, termo: str, dias: int) -> pd.DataFrame:
    return obter_cliente().pesquisar_produto(codigo_ibge, descricao=termo, dias=dias)


def buscar_cesta_basica(codigo_ibge: int, dias: int) -> tuple[pd.DataFrame, list[str]]:
    """Busca as ofertas da cesta básica (todas as marcas e NCMs), pelo termo de cada item.

    Devolve ``(ofertas, falhas)``. Se uma consulta falhar, as demais seguem; cada falha
    traz a mensagem da API, para o diagnóstico.
    """
    partes, falhas = [], []
    consultas = consultas_api()
    progresso = st.progress(0.0, text="Consultando a API…")
    for n, (item, termo) in enumerate(consultas, start=1):
        progresso.progress(n / len(consultas), text=f"Consultando {item} ({termo})…")
        try:
            df = _buscar_termo(codigo_ibge, termo, dias)
        except EconomizaAPIError as erro:
            falhas.append(f"{item} ({termo}): {erro}")
            continue
        if not df.empty:
            partes.append(df.assign(item=item))
    progresso.empty()
    ofertas = remover_duplicadas(pd.concat(partes, ignore_index=True)) if partes else pd.DataFrame()
    return ofertas, falhas


def seletor_produtos(ofertas: pd.DataFrame, item: str, unidade: str, chave: str) -> dict:
    """Filtro de produtos igual em todas as páginas: marca (texto) + lista do que foi encontrado.

    Devolve ``{"marca": texto, "produtos": [chaves]}``, pronto para ``produtos.filtrar_produtos``.
    A marca reduz a lista; sem marcar nenhum produto, valem todos os que contêm a marca.
    """
    from . import produtos

    c_marca, c_lista = st.columns([1, 3])
    marca = c_marca.text_input("Marca", key=f"m_{chave}", placeholder="ex.: skol",
                               help="Filtra pelo nome. Aceita mais de uma palavra, em qualquer ordem.")
    cat = produtos.catalogo(ofertas, item, unidade, marca)
    por_rotulo = dict(zip(cat["rotulo"], cat["produto"]))
    vazio = "Nenhum produto com essa marca" if marca and cat.empty else (
        f"Todos os {len(cat)} com \"{marca}\"" if marca else "Qualquer produto: usa o mais barato")
    marcados = c_lista.multiselect(f"Produtos ({len(cat)} encontrados)", list(por_rotulo),
                                   key=f"p_{chave}_{marca}", placeholder=vazio)
    return {"marca": marca, "produtos": [por_rotulo[r] for r in marcados]}


def rodape() -> None:
    st.divider()
    st.caption(
        "Dados: API pública [Economiza Alagoas](https://economizaalagoas.sefaz.al.gov.br) "
        "(SEFAZ-AL), a partir de notas fiscais eletrônicas. Desenvolvido por Capivara.inc."
    )
