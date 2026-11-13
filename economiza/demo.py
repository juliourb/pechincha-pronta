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

# Cesta básica: ofertas fictícias por NCM, com descrições no estilo das notas fiscais.
# (descrição, unidade de medida, preço). Algumas estão fora da especificação de propósito
# (café em grão, arroz parboilizado, banana-da-terra) para exercitar o filtro.
_OFERTAS_NCM: dict[str, list[tuple[str, str, float]]] = {
    "02013000": [("CARNE BOV PATINHO KG", "KG", 44.90), ("COXAO MOLE BOVINO KG", "KG", 46.90),
                 ("CARNE BOV COXAO DURO KG", "KG", 42.90), ("PICANHA BOVINA KG", "KG", 69.90)],
    "02023000": [("PATINHO BOVINO CONGELADO KG", "KG", 39.90)],
    "04012010": [("LEITE UHT INTEGRAL MARCA A 1L", "UN", 5.49), ("LEITE INTEGRAL MARCA B 1L", "UN", 5.89),
                 ("LEITE UHT DESNATADO MARCA A 1L", "UN", 5.69)],
    "07133399": [("FEIJAO CARIOCA T1 MARCA A 1KG", "UN", 8.49), ("FEIJAO CARIOCA MARCA B 1KG", "UN", 8.99),
                 ("FEIJAO MACASSAR MARCA C 1KG", "UN", 9.49)],
    "07133319": [],
    "10063021": [("ARROZ AGULHINHA T1 MARCA A 1KG", "UN", 6.49), ("ARROZ BRANCO T1 MARCA B 5KG", "UN", 29.90),
                 ("ARROZ PARBOILIZADO MARCA C 1KG", "UN", 6.29)],
    "11062000": [("FARINHA DE MANDIOCA MARCA A 1KG", "UN", 6.99), ("FARINHA MANDIOCA FINA MARCA B 500G", "UN", 3.79),
                 ("GOMA DE TAPIOCA MARCA C 1KG", "UN", 9.90)],
    "07020000": [("TOMATE KG", "KG", 7.99), ("TOMATE CEREJA BANDEJA 250G", "UN", 6.99)],
    "19059090": [("PAO FRANCES KG", "KG", 15.90), ("PAO CARIOQUINHA KG", "KG", 14.90),
                 ("BOLO DE MILHO FATIA", "UN", 4.50)],
    "09012100": [("CAFE TORRADO MOIDO MARCA A 250G", "UN", 11.90), ("CAFE MARCA B 500G", "UN", 22.90),
                 ("CAFE EM GRAO MARCA C 500G", "UN", 29.90)],
    "08039000": [("BANANA PRATA KG", "KG", 5.99), ("BANANA NANICA KG", "KG", 3.99),
                 ("BANANA DA TERRA KG", "KG", 7.49)],
    "17019900": [("ACUCAR CRISTAL MARCA A 1KG", "UN", 4.49), ("ACUCAR CRISTAL MARCA B 2KG", "UN", 8.79),
                 ("ACUCAR REFINADO MARCA C 1KG", "UN", 5.29)],
    "17011400": [],
    "15079011": [("OLEO DE SOJA MARCA A 900ML", "UN", 8.49), ("OLEO SOJA MARCA B 900 ML", "UN", 8.99)],
    "04051000": [("MANTEIGA COM SAL MARCA A 200G", "UN", 12.90), ("MANTEIGA MARCA B 500G", "UN", 29.90),
                 ("MARGARINA MARCA C 500G", "UN", 7.90)],
}


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
        if descricao is None and ncm in _OFERTAS_NCM:
            return self._cesta_basica(codigo_ibge, ncm, dias)
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

    def _cesta_basica(self, codigo_ibge: int, ncm: str, dias: int) -> pd.DataFrame:
        registros = []
        for i in range(1, 16):
            if i == 15 and ncm != "19059090":  # a loja 15 é uma padaria: só vende pão
                continue
            loja = _rng("loja-cesta", codigo_ibge, i)
            fator_loja = loja.uniform(0.90, 1.15)  # mercados mais baratos ou mais caros
            r = _rng("cesta", ncm, codigo_ibge, i)
            if r.random() < 0.12:  # nem toda loja vende tudo
                continue
            prefixo = "PADARIA" if i == 15 else "MERCADO"
            for j, (desc, unidade, preco) in enumerate(_OFERTAS_NCM[ncm]):
                if j > 0 and r.random() < 0.35:
                    continue
                valor = round(preco * fator_loja * r.uniform(0.95, 1.06), 2)
                registros.append({
                    "produto": {"codigo": f"{ncm}{j}", "descricao": desc, "ncm": ncm,
                                "gtin": f"789{zlib.crc32(desc.encode()):010d}", "unidadeMedida": unidade,
                                "venda": {"dataVenda": _data(r, dias), "valorDeclarado": valor,
                                          "valorVenda": valor}},
                    "estabelecimento": _estabelecimento(i, codigo_ibge, prefixo),
                })
        return normalizar_resultado(registros)
