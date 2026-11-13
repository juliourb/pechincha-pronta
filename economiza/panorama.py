"""Análises da cesta básica no estado inteiro, a partir de uma coleta."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .cesta_basica import brl, formatar_horas, horas_de_trabalho, numero_br
from .municipios import nome_oficial


def ranking(municipios: pd.DataFrame, minimo_lojas: int) -> pd.DataFrame:
    """Municípios com pelo menos ``minimo_lojas`` cestas completas, do mais barato ao mais caro,
    com a diferença (%) em relação à mediana estadual dos municípios."""
    r = municipios[municipios["com_cesta_completa"] >= minimo_lojas].copy()
    if r.empty:
        return r
    referencia = r["mediana"].median()
    r["pct_vs_estado"] = 100 * (r["mediana"] / referencia - 1)
    r["nome"] = r["municipio"].map(nome_oficial)
    return r.sort_values("mediana").reset_index(drop=True)


def correlacao_spearman(x: pd.Series, y: pd.Series) -> float:
    """Correlação de postos (Spearman), sem depender do scipy."""
    validos = x.notna() & y.notna()
    if validos.sum() < 3:
        return np.nan
    return float(x[validos].rank().corr(y[validos].rank()))


def descrever_correlacao(rho: float) -> str:
    if np.isnan(rho):
        return "dados insuficientes"
    forca = abs(rho)
    nivel = "muito fraca" if forca < 0.2 else "fraca" if forca < 0.4 else "moderada" if forca < 0.6 else "forte"
    sentido = "quanto mais lojas, mais barata" if rho < 0 else "quanto mais lojas, mais cara"
    return f"{nivel} ({sentido}; ρ = {numero_br(rho, 2)})"


def analise_estadual(rank: pd.DataFrame, lojas: pd.DataFrame, minimo_lojas: int) -> list[str]:
    """Frases-resumo do panorama estadual."""
    frases = []
    if rank.empty:
        return [f"Nenhum município tem {minimo_lojas} ou mais lojas com a cesta completa nesta coleta."]
    completas = lojas.loc[lojas["completa"], "cesta_min"]
    barato, caro = rank.iloc[0], rank.iloc[-1]
    frases.append(
        f"**{len(rank)}** municípios têm {minimo_lojas} ou mais lojas com a cesta completa; juntos, "
        f"somam {int(rank['com_cesta_completa'].sum())} estabelecimentos."
    )
    frases.append(
        f"A mediana estadual (todas as lojas com a cesta completa) é **{brl(completas.median())}**, "
        f"o equivalente a {formatar_horas(horas_de_trabalho(completas.median()))} de trabalho com um salário mínimo."
    )
    if len(rank) > 1:
        dif = caro["mediana"] - barato["mediana"]
        frases.append(
            f"A cesta mediana mais barata está em **{barato['nome']}** ({brl(barato['mediana'])}) e a mais cara em "
            f"**{caro['nome']}** ({brl(caro['mediana'])}): diferença de {brl(dif)} por mês "
            f"({numero_br(100 * dif / barato['mediana'], 0)}%)."
        )
    rho = correlacao_spearman(rank["com_cesta_completa"], rank["mediana"])
    if not np.isnan(rho):
        frases.append(f"Relação entre número de lojas e preço da cesta: {descrever_correlacao(rho)}.")
    return frases


def classes_quantis(valores: pd.Series, n: int = 5) -> list[float]:
    """Limites de classes por quantis (cada cor com quantidades parecidas de municípios)."""
    v = valores.dropna()
    if v.empty:
        return []
    limites = sorted(set(np.round(v.quantile(np.linspace(0, 1, n + 1)).values, 2)))
    return limites if len(limites) > 1 else [v.min(), v.max() + 0.01]
