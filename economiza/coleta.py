"""Coleta estadual da cesta básica e o seu armazenamento em Parquet.

Fluxo:
1. ``coletar`` consulta a API para cada município e item (19 consultas por município: termo + NCM de cada item);
2. ``montar_tabelas`` gera três tabelas: ``ofertas`` (cada oferta, já classificada),
   ``lojas`` (a cesta por estabelecimento) e ``municipios`` (indicadores);
3. ``salvar`` grava os Parquet, um ``manifesto.json`` (linhas e bytes de cada arquivo) e
   atualiza o índice ``coletas.json``, que guarda o histórico de todas as coletas.

Publicação (GitHub Actions, ``.github/workflows/coleta.yml``): cada coleta vira uma Release
``coleta-AAAA-MM-DD`` com os arquivos, e a Release fixa ``indice`` guarda o ``coletas.json``.
O app lê tudo por URLs públicas de download, sem gastar o limite da API do GitHub.
"""

from __future__ import annotations

import io
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from . import cesta_basica as cb
from .api import EconomizaAPIError
from .municipios import MUNICIPIOS_AL

REPOSITORIO = os.environ.get("PECHINCHA_REPO", "juliourb/pechincha-pronta")
PREFIXO_TAG = "coleta-"
TAG_INDICE = "indice"
INTERVALO_DIAS = 10  # coleta a cada 10 dias, consultando os 10 dias anteriores (limite da API)
COLETAS_POR_ANO = 365 / INTERVALO_DIAS
ARQUIVOS = ("ofertas", "lojas", "municipios")
_FUSO = ZoneInfo("America/Maceio")

# Colunas guardadas das ofertas: os dados "brutos" necessários para refazer a classificação
# no futuro (se as regras mudarem) + o resultado da classificação desta coleta.
COLUNAS_OFERTAS = [
    "data_coleta", "codigo_ibge", "municipio", "item", "ncm", "gtin", "descricao", "unidade_medida",
    "valor_declarado", "valor_venda", "data_venda", "preco_base", "tamanho_unitario", "motivo",
    "cnpj", "estabelecimento", "razao_social", "bairro", "logradouro", "numero", "cep",
    "latitude", "longitude",
]
_CATEGORICAS = ["municipio", "item", "ncm", "unidade_medida", "motivo", "bairro"]


def hoje() -> str:
    return datetime.now(_FUSO).date().isoformat()


# ------------------------------------------------------------------------------------ coleta
def baixar_municipio(cliente, codigo_ibge: int, dias: int, pausa: float = 0.0) -> tuple[pd.DataFrame, list[str]]:
    """Ofertas da cesta básica num município (termo + NCM de cada item). Devolve (ofertas, falhas)."""
    partes, falhas = [], []
    for item, termo, ncm in cb.consultas_api():
        try:
            df = cliente.pesquisar_produto(codigo_ibge, descricao=termo, ncm=ncm, dias=dias)
        except EconomizaAPIError as erro:
            falhas.append(f"{codigo_ibge}:{termo}:{ncm}: {erro}")
            df = pd.DataFrame()
        if not df.empty:
            partes.append(df.assign(item=item))
        if pausa:
            time.sleep(pausa)
    ofertas = cb.remover_duplicadas(pd.concat(partes, ignore_index=True)) if partes else pd.DataFrame()
    return ofertas, falhas


def coletar(cliente, municipios: list[str], dias: int = INTERVALO_DIAS, pausa: float = 0.0,
            progresso: Callable[[int, int, str], None] | None = None) -> tuple[pd.DataFrame, list[str], int]:
    """Coleta e classifica as ofertas de vários municípios.

    Devolve ``(ofertas, falhas, consultas)``.
    """
    partes, falhas = [], []
    consultas = 0
    for n, nome in enumerate(municipios, start=1):
        if progresso:
            progresso(n, len(municipios), nome)
        ibge = MUNICIPIOS_AL[nome]
        df, f = baixar_municipio(cliente, ibge, dias, pausa)
        consultas += len(cb.consultas_api())
        falhas += f
        if not df.empty:
            classificadas = cb.classificar_ofertas(df)
            partes.append(classificadas.assign(codigo_ibge=ibge, municipio=nome))
    ofertas = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=COLUNAS_OFERTAS)
    return ofertas, falhas, consultas


# ---------------------------------------------------------------------------------- tabelas
def montar_tabelas(ofertas: pd.DataFrame, data_coleta: str) -> dict[str, pd.DataFrame]:
    """Gera as tabelas ``ofertas``, ``lojas`` e ``municipios`` de uma coleta."""
    ofertas = ofertas.copy()
    ofertas["data_coleta"] = data_coleta
    for col in COLUNAS_OFERTAS:
        if col not in ofertas:
            ofertas[col] = pd.NA
    ofertas = ofertas[COLUNAS_OFERTAS]

    lojas = []
    for (ibge, nome), grupo in ofertas.groupby(["codigo_ibge", "municipio"], observed=True):
        cestas = cb.cestas_por_estabelecimento(grupo)
        if not cestas.empty:
            lojas.append(cestas.assign(codigo_ibge=ibge, municipio=nome))
    lojas = pd.concat(lojas, ignore_index=True) if lojas else pd.DataFrame()
    if not lojas.empty:
        lojas.insert(0, "data_coleta", data_coleta)

    municipios = cb.indicadores(lojas, por="municipio") if not lojas.empty else pd.DataFrame()
    if not municipios.empty:
        municipios.insert(0, "data_coleta", data_coleta)
        municipios.insert(2, "codigo_ibge", municipios["municipio"].map(MUNICIPIOS_AL))
    return {"ofertas": ofertas, "lojas": lojas, "municipios": municipios}


def _compactar(df: pd.DataFrame) -> pd.DataFrame:
    """Tipos menores e colunas categóricas: o Parquet fica bem menor."""
    df = df.copy()
    for col in _CATEGORICAS:
        if col in df:
            df[col] = df[col].astype("string").astype("category")
    for col in ("cnpj", "gtin", "descricao", "estabelecimento", "razao_social", "logradouro", "numero", "cep",
                "itens_faltando"):
        if col in df:
            df[col] = df[col].astype("string")
    if "data_venda" in df:
        df["data_venda"] = pd.to_datetime(df["data_venda"], errors="coerce")
    return df


def resumo_estadual(tabelas: dict[str, pd.DataFrame]) -> dict:
    """Indicadores do estado inteiro, guardados no índice para a série histórica."""
    lojas = tabelas["lojas"]
    completas = lojas.loc[lojas["completa"], "cesta_min"] if not lojas.empty else pd.Series(dtype=float)
    mun = tabelas["municipios"]
    return {
        "municipios_com_dados": int(mun["municipio"].nunique()) if not mun.empty else 0,
        "municipios_com_cesta": int((mun["com_cesta_completa"] > 0).sum()) if not mun.empty else 0,
        "lojas": int(len(lojas)),
        "lojas_com_cesta": int(len(completas)),
        "cesta_mediana": round(float(completas.median()), 2) if len(completas) else None,
        "cesta_menor": round(float(completas.min()), 2) if len(completas) else None,
        "cesta_maior": round(float(completas.max()), 2) if len(completas) else None,
    }


def salvar(tabelas: dict[str, pd.DataFrame], pasta: Path, extra: dict | None = None,
           indice_anterior: list[dict] | None = None) -> dict:
    """Grava os Parquet (zstd), o ``manifesto.json`` e o ``coletas.json`` atualizado."""
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos = {}
    for nome, df in tabelas.items():
        caminho = pasta / f"{nome}.parquet"
        _compactar(df).to_parquet(caminho, compression="zstd", index=False)
        arquivos[nome] = {"linhas": int(len(df)), "bytes": caminho.stat().st_size}
    manifesto = {**(extra or {}), "arquivos": arquivos, "estado": resumo_estadual(tabelas)}
    (pasta / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")

    indice = [c for c in (indice_anterior or []) if c.get("tag") != manifesto.get("tag")] + [manifesto]
    indice.sort(key=lambda c: c.get("data_coleta", ""))
    (pasta / "coletas.json").write_text(json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifesto


# ------------------------------------------------------------------------- leitura (app)
def _url(tag: str, arquivo: str) -> str:
    return f"https://github.com/{REPOSITORIO}/releases/download/{tag}/{arquivo}"


def ler_indice(pasta_local: Path | None = None, timeout: float = 20) -> list[dict]:
    """Lista de coletas publicadas (mais antiga primeiro). Vazia se ainda não houver."""
    if pasta_local:
        caminho = pasta_local / "coletas.json"
        return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else []
    resp = requests.get(_url(TAG_INDICE, "coletas.json"), timeout=timeout)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json()


def ler_tabela(coleta: dict, nome: str, pasta_local: Path | None = None, timeout: float = 60) -> pd.DataFrame:
    if pasta_local:
        return pd.read_parquet(pasta_local / coleta["tag"] / f"{nome}.parquet")
    resp = requests.get(_url(coleta["tag"], f"{nome}.parquet"), timeout=timeout)
    resp.raise_for_status()
    return pd.read_parquet(io.BytesIO(resp.content))


def url_download(coleta: dict, nome: str) -> str:
    return _url(coleta["tag"], f"{nome}.parquet")


def dias_desde_ultima_coleta(indice: list[dict]) -> int | None:
    """Dias desde a última coleta real (ignora as de demonstração). ``None`` se não houver."""
    datas = [c["data_coleta"] for c in indice if not c.get("demo") and c.get("data_coleta")]
    if not datas:
        return None
    return (datetime.now(_FUSO).date() - datetime.fromisoformat(max(datas)).date()).days


def tamanho_das_coletas(indice: list[dict]) -> pd.DataFrame:
    """Linhas e megabytes de cada coleta, por arquivo, para acompanhar o crescimento."""
    linhas = []
    for c in indice:
        for nome, info in c.get("arquivos", {}).items():
            linhas.append({"data_coleta": c.get("data_coleta"), "arquivo": nome,
                           "linhas": info["linhas"], "mb": info["bytes"] / 1e6})
    return pd.DataFrame(linhas)


def projecao_anual(indice: list[dict]) -> dict:
    """Projeção do espaço ocupado por ano, pela média das coletas já feitas."""
    tam = tamanho_das_coletas(indice)
    if tam.empty:
        return {}
    por_coleta = tam.groupby("data_coleta")["mb"].sum()
    return {"mb_por_coleta": por_coleta.mean(), "mb_por_ano": por_coleta.mean() * COLETAS_POR_ANO,
            "coletas": len(por_coleta), "mb_total": por_coleta.sum()}


# -------------------------------------------------------------------- malha municipal (mapa)
_FONTES_MALHA = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/27?intrarregiao=municipio"
    "&formato=application/vnd.geo%2Bjson&qualidade=intermediaria",
    "https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/geojs-27-mun.json",
)


def codigo_da_feicao(feicao: dict) -> int | None:
    """Código IBGE de um polígono, aceitando os nomes de campo das duas fontes."""
    p = feicao.get("properties", {})
    for chave in ("codarea", "id", "CD_MUN", "cod"):
        if p.get(chave):
            try:
                return int(str(p[chave])[:7])
            except ValueError:
                continue
    return None


def carregar_malha(timeout: float = 30) -> dict | None:
    """Malha municipal de Alagoas (GeoJSON). Tenta o IBGE e depois uma cópia pública."""
    for url in _FONTES_MALHA:
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.ok:
                malha = resp.json()
                if malha.get("features") and codigo_da_feicao(malha["features"][0]):
                    return malha
        except (requests.RequestException, ValueError):
            continue
    return None
