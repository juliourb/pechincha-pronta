"""Componentes de interface compartilhados entre as páginas do Streamlit."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import obter_cliente
from .api import EconomizaAPIError
from .cesta import CESTA_CHURRASCO
from .cesta_basica import ITENS_REGIAO_2
from .municipios import NOMES_MUNICIPIOS, normalizar

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
                        format_func=lambda n: n.title())


# @st.cache_data guarda o resultado da função: chamadas com os mesmos argumentos
# (mesmo combustível, município e período) não consultam a API de novo durante o TTL.
# O cache é compartilhado entre todos os usuários do app.
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def buscar_combustivel(tipo: int, codigo_ibge: int, dias: int) -> pd.DataFrame:
    return obter_cliente().pesquisar_combustivel(tipo, codigo_ibge, dias)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _buscar_produto(codigo_ibge: int, descricao: str, ncm: str, dias: int) -> pd.DataFrame:
    return obter_cliente().pesquisar_produto(codigo_ibge, descricao=descricao, ncm=ncm, dias=dias)


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
def _buscar_ncm(codigo_ibge: int, ncm: str, dias: int) -> pd.DataFrame:
    return obter_cliente().pesquisar_produto(codigo_ibge, ncm=ncm, dias=dias)


def buscar_cesta_basica(codigo_ibge: int, dias: int) -> tuple[pd.DataFrame, list[str]]:
    """Busca todas as ofertas dos NCMs da cesta básica (todas as marcas).

    Devolve ``(ofertas, falhas)``: se um NCM falhar, os demais seguem e o item fica
    listado em ``falhas`` (em vez de perder a consulta inteira).
    """
    partes, falhas = [], []
    consultas = [(item.nome, ncm) for item in ITENS_REGIAO_2 for ncm in item.ncms]
    progresso = st.progress(0.0, text="Consultando a API…")
    for n, (item, ncm) in enumerate(consultas, start=1):
        progresso.progress(n / len(consultas), text=f"Consultando {item} (NCM {ncm})…")
        try:
            df = _buscar_ncm(codigo_ibge, ncm, dias)
        except EconomizaAPIError:
            falhas.append(f"{item} (NCM {ncm})")
            continue
        if not df.empty:
            partes.append(df.assign(item=item))
    progresso.empty()
    ofertas = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    return ofertas, falhas


def rodape() -> None:
    st.divider()
    st.caption(
        "Dados: API pública [Economiza Alagoas](https://economizaalagoas.sefaz.al.gov.br) "
        "(SEFAZ-AL), a partir de notas fiscais eletrônicas. Desenvolvido por Capivara.inc."
    )
