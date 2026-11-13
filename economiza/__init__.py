"""Pechincha Pronta: consultas de preço na API Economiza Alagoas (SEFAZ-AL)."""

from __future__ import annotations

from .api import EconomizaAPIError, EconomizaClient, obter_token
from .demo import DemoClient


def obter_cliente() -> EconomizaClient | DemoClient:
    """Cliente real se houver token; caso contrário, o modo demonstração."""
    token = obter_token()
    return EconomizaClient(token) if token else DemoClient()


__all__ = ["DemoClient", "EconomizaAPIError", "EconomizaClient", "obter_cliente", "obter_token"]
