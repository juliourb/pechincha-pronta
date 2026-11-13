"""Cesta de churrasco: itens, subfiltros e menor total por estabelecimento.

Usa a mesma base da cesta básica (``cesta_basica.classificar_ofertas``): cada oferta tem
o tamanho da embalagem lido na descrição e o preço convertido para R$/kg ou R$/litro.
Assim dá para comparar lata com garrafa, saco de carvão de 3 kg com o de 5 kg, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from .cesta_basica import classificar_ofertas
from .municipios import normalizar

# Cortes bovinos desossados: frescos/refrigerados (0201.30.00) e congelados (0202.30.00).
_RESFRIADA, _CONGELADA = "02013000", "02023000"
_BOVINO = (_RESFRIADA, _CONGELADA)


@dataclass(frozen=True)
class Subfiltro:
    """Uma opção de refinamento. Todas as condições informadas precisam valer."""

    exige: str | None = None  # regex que a descrição precisa conter
    proibe: str | None = None  # regex que exclui a descrição
    tamanho_min: float | None = None  # tamanho unitário da embalagem (kg ou L)
    tamanho_max: float | None = None
    ncm: str | None = None


@dataclass(frozen=True)
class ItemChurrasco:
    nome: str
    ncms: tuple[str, ...]
    descricao_api: str  # termo enviado à API junto com o NCM
    unidade: str  # "kg" ou "L": a quantidade e o preço comparado usam esta unidade
    quantidade_padrao: float
    dica: str
    exige: str | None = None
    proibe: str | None = None
    subfiltros: dict[str, Subfiltro] = field(default_factory=dict)
    fatores_kg_para_dz: dict[str, float] = field(default_factory=dict)  # compatibilidade


_FORMATOS_CERVEJA = {
    "Lata 350 ml": Subfiltro(proibe=r"LONG|\bLN\b|GARRAFA|\bGFA\b|VIDRO", tamanho_min=0.33, tamanho_max=0.36),
    "Latinha 269 ml": Subfiltro(tamanho_min=0.25, tamanho_max=0.28),
    "Latão 473 ml": Subfiltro(tamanho_min=0.45, tamanho_max=0.50),
    "Long neck": Subfiltro(exige=r"LONG|\bLN\b", tamanho_min=0.25, tamanho_max=0.36),
    "Garrafa 600 ml": Subfiltro(tamanho_min=0.55, tamanho_max=0.65),
    "Litrão 1 L": Subfiltro(tamanho_min=0.95, tamanho_max=1.05),
}
_CARNE = {
    "Resfriada": Subfiltro(ncm=_RESFRIADA),
    "Congelada": Subfiltro(ncm=_CONGELADA),
    "Sem tempero": Subfiltro(proibe=r"TEMPERAD|MARINAD"),
}
_NAO_CARNE = r"SUIN|PORCO|FRANGO|HAMBURG|MOID|ALMONDEG|LINGUI"

CESTA_CHURRASCO: dict[str, ItemChurrasco] = {
    "Picanha": ItemChurrasco("Picanha", _BOVINO, "PICANHA", "kg", 1.0, "kg de carne",
                             exige=r"PICANHA", proibe=_NAO_CARNE, subfiltros=_CARNE),
    "Alcatra": ItemChurrasco("Alcatra", _BOVINO, "ALCATRA", "kg", 1.0, "kg de carne",
                             exige=r"ALCATRA", proibe=_NAO_CARNE, subfiltros=_CARNE),
    "Fraldinha": ItemChurrasco("Fraldinha", _BOVINO, "FRALDINHA", "kg", 1.0, "kg de carne",
                               exige=r"FRALD", proibe=_NAO_CARNE, subfiltros=_CARNE),
    "Cupim": ItemChurrasco("Cupim", _BOVINO, "CUPIM", "kg", 1.0, "kg de carne",
                           exige=r"CUPIM", proibe=_NAO_CARNE, subfiltros=_CARNE),
    "Coxão mole": ItemChurrasco("Coxão mole", _BOVINO, "COXAO MOLE", "kg", 1.0, "kg de carne",
                                exige=r"\bCO?X(AO|\.)? ?MOLE|\bCHA (DE )?DENTRO", proibe=_NAO_CARNE,
                                subfiltros=_CARNE),
    "Cerveja": ItemChurrasco("Cerveja", ("22030000",), "CERVEJA", "L", 4.2,
                             "litros (12 latas de 350 ml = 4,2 L)",
                             exige=r"CERV|CHOPP|PILSEN", proibe=r"SEM ALCOOL|ZERO|0,0|\b0\.0",
                             subfiltros=_FORMATOS_CERVEJA),
    "Cerveja sem álcool": ItemChurrasco("Cerveja sem álcool", ("22029100",), "CERVEJA SEM ALCOOL", "L", 2.1,
                                        "litros (6 latas de 350 ml = 2,1 L)", subfiltros=_FORMATOS_CERVEJA),
    "Carvão": ItemChurrasco("Carvão", ("44029000",), "CARVAO", "kg", 3.0, "kg (um saco comum tem 3 a 5 kg)",
                            exige=r"CARV", subfiltros={
                                "Saco até 3 kg": Subfiltro(tamanho_max=3.0),
                                "Saco de 4 kg ou mais": Subfiltro(tamanho_min=4.0)}),
    "Farofa": ItemChurrasco("Farofa", ("19019090",), "FAROFA", "kg", 0.5, "kg (pacote comum: 250 a 500 g)",
                            exige=r"FAROFA", subfiltros={
                                "Temperada / pronta": Subfiltro(exige=r"TEMPER|PRONTA|BACON|CEBOLA|ALHO")}),
    "Pão de alho": ItemChurrasco("Pão de alho", ("19059090",), "PAO DE ALHO", "kg", 0.4,
                                 "kg (pacote comum: 300 a 400 g)", exige=r"PAO (DE )?ALHO", subfiltros={
                                     "Tradicional": Subfiltro(proibe=r"QUEIJO|RECHE|COMPLETO|PICANT|CALABR"),
                                     "Com queijo ou recheado": Subfiltro(exige=r"QUEIJO|RECHE|COMPLETO")}),
    "Queijo coalho": ItemChurrasco("Queijo coalho", ("04069010", "04069020", "04069030", "04069090"),
                                   "QUEIJO COALHO", "kg", 0.5, "kg (espeto com 7 unidades ≈ 400 g)",
                                   exige=r"COALHO", subfiltros={
                                       "Espeto / palito": Subfiltro(exige=r"ESPET|SPETO|PALITO|\bESP\b"),
                                       "Barra / peça": Subfiltro(proibe=r"ESPET|SPETO|PALITO|\bESP\b")}),
}


def classificar_churrasco(df: pd.DataFrame) -> pd.DataFrame:
    """Converte cada oferta para R$/kg ou R$/L e marca as fora do item (ex.: picanha suína)."""
    return classificar_ofertas(df, CESTA_CHURRASCO)


def _atende(linhas: pd.DataFrame, sub: Subfiltro) -> pd.Series:
    ok = pd.Series(True, index=linhas.index)
    desc = linhas["descricao"].map(normalizar)
    if sub.exige:
        ok &= desc.str.contains(sub.exige, regex=True)
    if sub.proibe:
        ok &= ~desc.str.contains(sub.proibe, regex=True)
    if sub.tamanho_min is not None:
        ok &= linhas["tamanho_unitario"] >= sub.tamanho_min
    if sub.tamanho_max is not None:
        ok &= linhas["tamanho_unitario"] <= sub.tamanho_max
    if sub.ncm:
        ok &= linhas["ncm"].astype(str) == sub.ncm
    return ok.fillna(False)


def filtrar_ofertas(ofertas: pd.DataFrame, filtros: dict[str, dict] | None = None) -> pd.DataFrame:
    """Aplica, item a item, o subfiltro escolhido e o texto de marca/descrição.

    ``filtros``: item -> {"subfiltro": nome ou None, "texto": "heineken" ou ""}.
    """
    validas = ofertas[ofertas["motivo"] == "ok"]
    if not filtros:
        return validas
    manter = pd.Series(True, index=validas.index)
    for item, escolha in filtros.items():
        do_item = validas["item"] == item
        if not do_item.any():
            continue
        linhas = validas[do_item]
        ok = pd.Series(True, index=linhas.index)
        sub = CESTA_CHURRASCO[item].subfiltros.get(escolha.get("subfiltro") or "")
        if sub:
            ok &= _atende(linhas, sub)
        texto = normalizar(escolha.get("texto"))
        if texto:
            ok &= linhas["descricao"].map(normalizar).str.contains(re.escape(texto), regex=True)
        manter[linhas.index] = ok
    return validas[manter]


def montar_carrinho(ofertas: pd.DataFrame, quantidades: dict[str, float]) -> pd.DataFrame:
    """Opção mais barata (por kg ou litro) de cada item em cada estabelecimento.

    ``ofertas`` já classificadas e filtradas; ``quantidades``: item -> kg ou litros.
    Só entram estabelecimentos que vendem **todos** os itens.
    """
    colunas = ["cnpj", "estabelecimento", "item", "descricao", "valor_declarado", "preco_base",
               "unidade", "quantidade", "valor_item", "data_venda"]
    itens = list(quantidades)
    validas = ofertas[(ofertas["motivo"] == "ok") & ofertas["item"].isin(itens)] if not ofertas.empty else ofertas
    if not itens or validas.empty or not set(itens) <= set(validas["item"]):
        return pd.DataFrame(columns=colunas)

    melhor = (validas.sort_values(["preco_base", "data_venda"], ascending=[True, False])
              .drop_duplicates(["cnpj", "item"], keep="first"))
    completos = melhor.groupby("cnpj")["item"].nunique()
    carrinho = melhor[melhor["cnpj"].isin(completos[completos == len(itens)].index)].copy()
    carrinho["quantidade"] = carrinho["item"].map(quantidades).astype(float)
    carrinho["unidade"] = carrinho["item"].map(lambda i: CESTA_CHURRASCO[i].unidade)
    carrinho["valor_item"] = (carrinho["preco_base"] * carrinho["quantidade"]).round(2)
    return carrinho[colunas].sort_values(["estabelecimento", "item"]).reset_index(drop=True)


def total_por_estabelecimento(carrinho: pd.DataFrame, ofertas: pd.DataFrame) -> pd.DataFrame:
    """Valor total da cesta por estabelecimento, com endereço e coordenadas."""
    colunas_local = ["cnpj", "estabelecimento", "logradouro", "numero", "bairro", "municipio",
                     "latitude", "longitude"]
    if carrinho.empty:
        return pd.DataFrame(columns=["valor_cesta", "ultima_nota", *colunas_local])
    totais = carrinho.groupby("cnpj").agg(valor_cesta=("valor_item", "sum"), ultima_nota=("data_venda", "max"))
    totais["valor_cesta"] = totais["valor_cesta"].round(2)
    disponiveis = [c for c in colunas_local if c in ofertas.columns]
    locais = (ofertas[disponiveis].sort_values("latitude", na_position="last")
              .drop_duplicates("cnpj").set_index("cnpj"))
    return totais.join(locais, how="left").reset_index().sort_values("valor_cesta").reset_index(drop=True)


def resumo_por_item(ofertas: pd.DataFrame) -> pd.DataFrame:
    """Quantas ofertas e lojas sobram por item depois dos filtros (feedback na tela)."""
    if ofertas.empty:
        return pd.DataFrame(columns=["item", "ofertas", "lojas", "menor_preco"])
    return (ofertas.groupby("item")
            .agg(ofertas=("descricao", "size"), lojas=("cnpj", "nunique"), menor_preco=("preco_base", "min"))
            .reset_index())
