"""Cliente da API pública Economiza Alagoas (SEFAZ-AL).

Documentação oficial: https://economizaalagoas.sefaz.al.gov.br/desenvolvedor.htm
O token de acesso é pessoal e deve ser solicitado à SEFAZ-AL (api@sefaz.al.gov.br).
"""

from __future__ import annotations

import os
import time
from typing import Any

import pandas as pd
import requests

from .municipios import normalizar

BASE_URL = os.environ.get(
    "ECONOMIZA_AL_BASE_URL",
    "http://api.sefaz.al.gov.br/sfz-economiza-alagoas-api/api/public",
)

# Códigos de combustível aceitos pela API.
TIPOS_COMBUSTIVEL: dict[str, int] = {
    "Gasolina Comum": 1,
    "Gasolina Aditivada": 2,
    "Álcool": 3,
    "Diesel Comum": 4,
    "Diesel Aditivado (S10)": 5,
    "GNV": 6,
}

DIAS_MAXIMO = 10
REGISTROS_POR_PAGINA = 5000
MAX_PAGINAS = 20  # trava de segurança contra laços infinitos
TENTATIVAS = 3  # 1 tentativa + 2 repetições em falhas temporárias do servidor
ERROS_TEMPORARIOS = {500, 502, 503, 504}

COLUNAS = {
    "produto.codigo": "codigo_produto",
    "produto.descricao": "descricao",
    "produto.descricaoSefaz": "descricao_sefaz",
    "produto.gpc": "gpc",
    "produto.gtin": "gtin",
    "produto.ncm": "ncm",
    "produto.unidadeMedida": "unidade_medida",
    "produto.venda.dataVenda": "data_venda",
    "produto.venda.valorDeclarado": "valor_declarado",
    "produto.venda.valorVenda": "valor_venda",
    "estabelecimento.cnpj": "cnpj",
    "estabelecimento.razaoSocial": "razao_social",
    "estabelecimento.nomeFantasia": "nome_fantasia",
    "estabelecimento.telefone": "telefone",
    "estabelecimento.endereco.codigoIBGE": "codigo_ibge",
    "estabelecimento.endereco.nomeLogradouro": "logradouro",
    "estabelecimento.endereco.numeroImovel": "numero",
    "estabelecimento.endereco.bairro": "bairro",
    "estabelecimento.endereco.cep": "cep",
    "estabelecimento.endereco.municipio": "municipio",
    "estabelecimento.endereco.latitude": "latitude",
    "estabelecimento.endereco.longitude": "longitude",
}


class EconomizaAPIError(RuntimeError):
    """Erro de comunicação com a API (HTTP != 200, timeout, JSON inválido...)."""


def obter_token() -> str | None:
    """Lê o token de ``st.secrets`` ou da variável de ambiente ``ECONOMIZA_AL_TOKEN``."""
    token = os.environ.get("ECONOMIZA_AL_TOKEN")
    if token:
        return token
    try:
        import streamlit as st

        return st.secrets.get("ECONOMIZA_AL_TOKEN")  # type: ignore[no-any-return]
    except Exception:  # sem secrets.toml ou fora do Streamlit
        return None


def normalizar_resultado(registros: list[dict[str, Any]]) -> pd.DataFrame:
    """Achata o JSON da API em tabela e padroniza nomes e tipos das colunas."""
    df = pd.json_normalize(registros)
    if df.empty:
        return pd.DataFrame(columns=list(COLUNAS.values()))
    df = df.rename(columns=COLUNAS)
    for col in ("valor_declarado", "valor_venda", "latitude", "longitude"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "data_venda" in df:
        # A API informa as datas em UTC (manual, seção 5): converte para o horário de Alagoas.
        datas = pd.to_datetime(df["data_venda"], errors="coerce", utc=True)
        df["data_venda"] = datas.dt.tz_convert("America/Maceio").dt.tz_localize(None)
    for col in ("ncm", "gtin", "cnpj"):
        if col in df:
            df[col] = df[col].astype("string")
    # Coordenadas (0, 0) significam "sem coordenada" na nota fiscal.
    if {"latitude", "longitude"} <= set(df.columns):
        sem_coord = (df["latitude"] == 0) | (df["longitude"] == 0)
        df.loc[sem_coord, ["latitude", "longitude"]] = pd.NA
    vazio = pd.Series(pd.NA, index=df.index, dtype="object")
    nome_fantasia = df.get("nome_fantasia", vazio).replace("", pd.NA)
    df["estabelecimento"] = nome_fantasia.fillna(df.get("razao_social", vazio))
    return df


def filtrar_bairro(df: pd.DataFrame, bairro: str | None) -> pd.DataFrame:
    """Filtro por bairro tolerante a acento/maiúscula e a nomes parciais."""
    alvo = normalizar(bairro)
    if not alvo or df.empty or "bairro" not in df:
        return df
    return df[df["bairro"].map(normalizar).str.contains(alvo, regex=False)]


def _mensagem_erro(status: int, corpo: str) -> str:
    """Traduz o erro HTTP da API para uma mensagem que o usuário entende."""
    detalhe = f"(HTTP {status}: {corpo[:200]})"
    if status in (401, 403):
        return f"O token da API foi recusado: confira ECONOMIZA_AL_TOKEN ou peça um novo à SEFAZ-AL. {detalhe}"
    if status in ERROS_TEMPORARIOS:
        return (
            "O serviço da SEFAZ-AL está fora do ar ou sobrecarregado no momento. O problema é "
            f"do lado do servidor, não do app: tente novamente mais tarde. {detalhe}"
        )
    return f"A API recusou a consulta. {detalhe}"


class EconomizaClient:
    def __init__(
        self,
        token: str,
        base_url: str = BASE_URL,
        timeout: float = 30,
        session: requests.Session | None = None,
    ) -> None:
        if not token:
            raise ValueError("Token da API Economiza Alagoas não configurado.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"AppToken": token, "Content-Type": "application/json"})

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST com novas tentativas (1 s, 2 s) quando o servidor falha temporariamente."""
        url = f"{self.base_url}/{endpoint}"
        for tentativa in range(1, TENTATIVAS + 1):
            ultima = tentativa == TENTATIVAS
            try:
                resp = self.session.post(url, json=payload, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if ultima:
                    raise EconomizaAPIError(
                        "Não foi possível conectar à API da SEFAZ-AL (sem resposta ou "
                        "tempo esgotado). Tente novamente em alguns minutos."
                    ) from exc
            except requests.RequestException as exc:
                raise EconomizaAPIError(f"Falha de conexão com a API: {exc}") from exc
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise EconomizaAPIError("A API retornou uma resposta que não é JSON.") from exc
                if resp.status_code not in ERROS_TEMPORARIOS or ultima:
                    raise EconomizaAPIError(_mensagem_erro(resp.status_code, resp.text))
            time.sleep(2 ** (tentativa - 1))
        raise AssertionError("inalcançável")

    def _paginar(self, endpoint: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Percorre todas as páginas. Usa ``totalPaginas`` quando a API informa."""
        registros: list[dict[str, Any]] = []
        for pagina in range(1, MAX_PAGINAS + 1):
            dados = self._post(
                endpoint,
                {**payload, "pagina": pagina, "registrosPorPagina": REGISTROS_POR_PAGINA},
            )
            conteudo = dados.get("conteudo") or []
            registros.extend(conteudo)
            total_paginas = dados.get("totalPaginas")
            if total_paginas is not None:
                if pagina >= int(total_paginas):
                    break
            elif len(conteudo) < REGISTROS_POR_PAGINA:
                break
        return registros

    def pesquisar_combustivel(self, tipo: int, codigo_ibge: int, dias: int = 7) -> pd.DataFrame:
        payload = {
            "produto": {"tipoCombustivel": int(tipo)},
            "estabelecimento": {"municipio": {"codigoIBGE": int(codigo_ibge)}},
            "dias": min(max(int(dias), 1), DIAS_MAXIMO),
        }
        return normalizar_resultado(self._paginar("combustivel/pesquisa", payload))

    def pesquisar_produto(
        self,
        codigo_ibge: int,
        descricao: str | None = None,
        ncm: str | None = None,
        gtin: str | None = None,
        dias: int = 7,
    ) -> pd.DataFrame:
        produto = {
            k: v
            for k, v in {"descricao": normalizar(descricao) or None, "ncm": ncm, "gtin": gtin}.items()
            if v
        }
        if not produto:
            raise ValueError("Informe descrição, NCM ou GTIN do produto.")
        payload = {
            "produto": produto,
            "estabelecimento": {"municipio": {"codigoIBGE": int(codigo_ibge)}},
            "dias": min(max(int(dias), 1), DIAS_MAXIMO),
        }
        return normalizar_resultado(self._paginar("produto/pesquisa", payload))
