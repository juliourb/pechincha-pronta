"""Regras da cesta de compras: menor preço por item e total por estabelecimento."""

from __future__ import annotations

import pandas as pd

# Cortes bovinos desossados: frescos/refrigerados (0201.30.00) e congelados (0202.30.00).
_BOVINO_DESOSSADO = ["02013000", "02023000"]

# Item da cesta -> códigos NCM (8 dígitos) usados na pesquisa.
# Códigos conferidos na Tabela NCM vigente (data/Tabela_NCM_Vigente_20240406.xlsx).
CESTA_CHURRASCO: dict[str, list[str]] = {
    "Cerveja": ["22030000"],
    "Cerveja sem álcool": ["22029100"],
    "Carvão": ["44029000"],
    "Farofa": ["19019090"],
    "Picanha": _BOVINO_DESOSSADO,
    "Alcatra": _BOVINO_DESOSSADO,
    "Fraldinha": _BOVINO_DESOSSADO,
    "Cupim": _BOVINO_DESOSSADO,
    "Coxão mole": _BOVINO_DESOSSADO,
    "Pão de alho": ["19059090"],
    # Queijos: massa dura, semidura, macia e "outros".
    "Queijo coalho": ["04069010", "04069020", "04069030", "04069090"],
}


def opcoes_por_item(df: pd.DataFrame) -> dict[str, list[str]]:
    """Descrições (marcas/apresentações) encontradas para cada item da cesta."""
    if df.empty:
        return {}
    return {
        item: sorted(grupo["descricao"].dropna().unique())
        for item, grupo in df.groupby("item", sort=True)
    }


def montar_carrinho(
    df: pd.DataFrame,
    quantidades: dict[str, float],
    escolhas: dict[str, str | None] | None = None,
) -> pd.DataFrame:
    """Menor preço de cada item em cada estabelecimento.

    - ``quantidades``: item -> quantidade (kg, unidades...). Define os itens da cesta.
    - ``escolhas``: item -> descrição exata desejada (``None`` = o mais barato).

    Só entram estabelecimentos que vendem **todos** os itens da cesta.
    Empates de preço são resolvidos pela nota fiscal mais recente.
    """
    itens = list(quantidades)
    if not itens or df.empty or not set(itens) <= set(df["item"]):
        return pd.DataFrame(
            columns=["cnpj", "estabelecimento", "item", "descricao", "valor_venda",
                     "quantidade", "valor_item", "data_venda"]
        )

    dados = df[df["item"].isin(itens) & df["valor_venda"].notna()].copy()
    for item, descricao in (escolhas or {}).items():
        if descricao:
            dados = dados[(dados["item"] != item) | (dados["descricao"] == descricao)]

    dados = dados.sort_values(["valor_venda", "data_venda"], ascending=[True, False])
    melhor = dados.drop_duplicates(["cnpj", "item"], keep="first")

    completos = melhor.groupby("cnpj")["item"].nunique()
    completos = completos[completos == len(itens)].index
    carrinho = melhor[melhor["cnpj"].isin(completos)].copy()

    carrinho["quantidade"] = carrinho["item"].map(quantidades).astype(float)
    carrinho["valor_item"] = (carrinho["valor_venda"] * carrinho["quantidade"]).round(2)
    colunas = ["cnpj", "estabelecimento", "item", "descricao", "valor_venda",
               "quantidade", "valor_item", "data_venda"]
    return carrinho[colunas].sort_values(["estabelecimento", "item"]).reset_index(drop=True)


def total_por_estabelecimento(carrinho: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Valor total da cesta por estabelecimento, com endereço e coordenadas."""
    colunas_local = ["cnpj", "estabelecimento", "telefone", "logradouro", "numero",
                     "bairro", "municipio", "latitude", "longitude"]
    if carrinho.empty:
        return pd.DataFrame(columns=["valor_cesta", "ultima_nota", *colunas_local])

    totais = carrinho.groupby("cnpj").agg(
        valor_cesta=("valor_item", "sum"), ultima_nota=("data_venda", "max")
    )
    totais["valor_cesta"] = totais["valor_cesta"].round(2)

    disponiveis = [c for c in colunas_local if c in df.columns]
    locais = (
        df[disponiveis]
        .sort_values("latitude", na_position="last")  # prefere a linha com coordenada
        .drop_duplicates("cnpj")
        .set_index("cnpj")
    )
    resultado = totais.join(locais, how="left").reset_index()
    return resultado.sort_values("valor_cesta").reset_index(drop=True)
