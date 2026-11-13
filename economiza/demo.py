"""Modo demonstração: dados FICTÍCIOS no mesmo formato da API.

Usado quando não há token configurado, para que o app (e os testes) funcionem
sem acesso à API da SEFAZ-AL. Nenhum valor aqui corresponde a preços reais.
"""

from __future__ import annotations

import random
import zlib
from datetime import datetime, timedelta

import pandas as pd

from .api import normalizar_resultado
from .municipios import MUNICIPIOS_AL

_CENTRO = (-9.6498, -35.7089)  # posição ilustrativa (Maceió) usada para todos os municípios
_PRECO_COMBUSTIVEL = {1: 6.29, 2: 6.49, 3: 4.59, 4: 6.09, 5: 6.19, 6: 4.99}
_PRECO_PRODUTO = {
    "CERVEJA": (3.49, "UN"), "CERVEJA SEM ALCOOL": (4.29, "UN"), "CARVAO": (18.90, "UN"),
    "FAROFA": (6.50, "UN"), "PICANHA": (69.90, "KG"), "ALCATRA": (44.90, "KG"),
    "FRALDINHA": (39.90, "KG"), "CUPIM": (36.90, "KG"), "COXAO MOLE": (42.90, "KG"),
    "PAO DE ALHO": (12.90, "UN"), "QUEIJO COALHO": (8.90, "UN"),
}
_MARCAS = ["MARCA A", "MARCA B", "MARCA C"]


def _rng(*partes: object) -> random.Random:
    return random.Random(zlib.crc32("|".join(map(str, partes)).encode()))


def _municipio(codigo_ibge: int) -> str:
    return next((n for n, c in MUNICIPIOS_AL.items() if c == codigo_ibge), "MACEIO")


def _estabelecimento(i: int, codigo_ibge: int, prefixo: str) -> dict:
    r = _rng("loja", codigo_ibge, prefixo, i)
    tem_coord = i % 5 != 4  # ~20% sem coordenada, como acontece nas notas reais
    return {
        "cnpj": f"{codigo_ibge % 100000:05d}{i:03d}000100",
        "razaoSocial": f"{prefixo} DEMO {i:02d} LTDA",
        "nomeFantasia": f"{prefixo} Demo {i:02d}",
        "telefone": None,
        "endereco": {
            "codigoIBGE": codigo_ibge,
            "nomeLogradouro": f"RUA FICTICIA {i}",
            "numeroImovel": str(10 * i),
            "bairro": ["CENTRO", "PONTA VERDE", "FAROL", "JATIUCA"][i % 4],
            "cep": "57000000",
            "municipio": _municipio(codigo_ibge),
            "latitude": _CENTRO[0] + r.uniform(-0.04, 0.04) if tem_coord else 0,
            "longitude": _CENTRO[1] + r.uniform(-0.04, 0.04) if tem_coord else 0,
        },
    }


def _data(r: random.Random, dias: int) -> str:
    return (datetime(2026, 1, 15, 12) - timedelta(hours=r.randint(0, dias * 24))).isoformat()


class DemoClient:
    """Mesma interface de ``EconomizaClient``, com dados gerados localmente."""

    demo = True

    def pesquisar_combustivel(self, tipo: int, codigo_ibge: int, dias: int = 7) -> pd.DataFrame:
        registros = []
        for i in range(1, 13):
            r = _rng("comb", tipo, codigo_ibge, i)
            preco = round(_PRECO_COMBUSTIVEL[tipo] + r.uniform(-0.40, 0.40), 2)
            registros.append({
                "produto": {"codigo": str(tipo), "descricao": f"COMBUSTIVEL TIPO {tipo}",
                            "unidadeMedida": "L",
                            "venda": {"dataVenda": _data(r, dias), "valorDeclarado": preco,
                                      "valorVenda": preco}},
                "estabelecimento": _estabelecimento(i, codigo_ibge, "POSTO"),
            })
        return normalizar_resultado(registros)

    def pesquisar_produto(self, codigo_ibge: int, descricao: str | None = None,
                          ncm: str | None = None, gtin: str | None = None,
                          dias: int = 7) -> pd.DataFrame:
        descricao = (descricao or "PRODUTO").upper()
        base, unidade = _PRECO_PRODUTO.get(descricao, (10.0, "UN"))
        registros = []
        for i in range(1, 11):
            r = _rng("prod", descricao, ncm, codigo_ibge, i)
            if r.random() < 0.15:  # nem toda loja vende tudo
                continue
            for j, marca in enumerate(_MARCAS[: r.randint(1, 3)]):
                preco = round(base * r.uniform(0.85, 1.20), 2)
                registros.append({
                    "produto": {"codigo": f"{i}{j}", "descricao": f"{descricao} {marca} {unidade}",
                                "gtin": f"789{zlib.crc32((descricao + marca).encode()):010d}",
                                "ncm": ncm, "unidadeMedida": unidade,
                                "venda": {"dataVenda": _data(r, dias), "valorDeclarado": preco,
                                          "valorVenda": preco}},
                    "estabelecimento": _estabelecimento(i, codigo_ibge, "MERCADO"),
                })
        return normalizar_resultado(registros)
