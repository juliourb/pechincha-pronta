"""Análises da cesta básica no estado inteiro, a partir de uma coleta."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .cesta_basica import brl, formatar_horas, horas_de_trabalho, numero_br
from .municipios import nome_oficial


def ranking(municipios: pd.DataFrame, max_estimados: int = 3, minimo_lojas_item: float = 1) -> pd.DataFrame:
    """Municípios com a cesta municipal calculada, do mais barato ao mais caro.

    - ``max_estimados``: quantos itens sem preço local (estimados pela mediana do estado) aceitar;
    - ``minimo_lojas_item``: mediana de lojas por item exigida (com 1 loja a cesta é frágil).
    Acrescenta a diferença (%) em relação à mediana dos municípios listados.
    """
    if "cesta" not in municipios:
        return municipios.iloc[0:0]
    r = municipios[municipios["cesta"].notna() & (municipios["itens_imputados"] <= max_estimados)
                   & (municipios["lojas_por_item"] >= minimo_lojas_item)].copy()
    if r.empty:
        return r
    r["pct_vs_estado"] = 100 * (r["cesta"] / r["cesta"].median() - 1)
    r["nome"] = r["municipio"].map(nome_oficial)
    r["situacao"] = r["itens_imputados"].map(lambda n: "completa" if n == 0 else f"{int(n)} item(ns) estimado(s)")
    return r.sort_values("cesta").reset_index(drop=True)


def correlacao_spearman(x: pd.Series, y: pd.Series) -> float:
    """Correlação de postos (Spearman), sem depender do scipy."""
    validos = x.notna() & y.notna()
    if validos.sum() < 3 or x[validos].nunique() < 2 or y[validos].nunique() < 2:
        return np.nan
    return float(x[validos].rank().corr(y[validos].rank()))


def descrever_correlacao(rho: float) -> str:
    if np.isnan(rho):
        return "dados insuficientes"
    forca = abs(rho)
    nivel = "muito fraca" if forca < 0.2 else "fraca" if forca < 0.4 else "moderada" if forca < 0.6 else "forte"
    sentido = "quanto mais lojas, mais barata" if rho < 0 else "quanto mais lojas, mais cara"
    return f"{nivel} ({sentido}; ρ = {numero_br(rho, 2)})"


def analise_estadual(rank: pd.DataFrame) -> list[str]:
    """Frases-resumo do panorama estadual."""
    if rank.empty:
        return ["Nenhum município atende aos critérios escolhidos nesta coleta."]
    frases = []
    completas = int((rank["itens_imputados"] == 0).sum())
    mediana = rank["cesta"].median()
    barato, caro = rank.iloc[0], rank.iloc[-1]
    frases.append(
        f"**{len(rank)}** municípios têm a cesta calculada: **{completas}** com os 12 itens encontrados "
        f"no próprio município e {len(rank) - completas} com até 3 itens estimados pela mediana do estado."
    )
    frases.append(
        f"A cesta mediana entre os municípios é **{brl(mediana)}**, o equivalente a "
        f"{formatar_horas(horas_de_trabalho(mediana))} de trabalho com um salário mínimo."
    )
    if len(rank) > 1:
        dif = caro["cesta"] - barato["cesta"]
        frases.append(
            f"A cesta mais barata está em **{barato['nome']}** ({brl(barato['cesta'])}) e a mais cara em "
            f"**{caro['nome']}** ({brl(caro['cesta'])}): diferença de {brl(dif)} por mês "
            f"({numero_br(100 * dif / barato['cesta'], 0)}%)."
        )
    if "cesta_economica" in rank and rank["cesta_economica"].notna().any():
        economia = (1 - rank["cesta_economica"] / rank["cesta"]).median()
        frases.append(
            f"Pesquisar preços compensa: comprando cada item onde ele é barato, a cesta fica em média "
            f"{numero_br(100 * economia, 0)}% mais barata que pelo preço típico do município."
        )
    rho = correlacao_spearman(rank["estabelecimentos"], rank["cesta"])
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
