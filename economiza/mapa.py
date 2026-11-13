"""Mapas (folium) e exportação GeoJSON dos resultados."""

from __future__ import annotations

import json
import math
from typing import Any

import folium
import pandas as pd


def com_coordenadas(df: pd.DataFrame) -> pd.DataFrame:
    """Linhas com latitude/longitude válidas (não nulas e dentro dos limites)."""
    if df.empty or not {"latitude", "longitude"} <= set(df.columns):
        return df.iloc[0:0]
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    validas = lat.between(-90, 90) & lon.between(-180, 180) & (lat != 0) & (lon != 0)
    return df[validas]


def criar_mapa(df: pd.DataFrame, coluna_valor: str, coluna_nome: str = "estabelecimento") -> folium.Map | None:
    """Um marcador por estabelecimento; o(s) mais barato(s) em vermelho.

    O enquadramento usa ``fit_bounds`` para mostrar todos os pontos,
    em vez de um zoom fixo.
    """
    pontos = com_coordenadas(df).drop_duplicates(subset=["latitude", "longitude", coluna_nome])
    if pontos.empty:
        return None

    menor = pontos[coluna_valor].min()
    mapa = folium.Map(tiles="OpenStreetMap", control_scale=True)
    for _, linha in pontos.iterrows():
        valor = linha[coluna_valor]
        mais_barato = math.isclose(valor, menor)
        nome = linha.get(coluna_nome) or "Sem nome"
        endereco = ", ".join(
            str(linha[c]) for c in ("logradouro", "numero", "bairro") if c in linha and pd.notna(linha[c])
        )
        folium.Marker(
            location=[linha["latitude"], linha["longitude"]],
            tooltip=f"R$ {valor:.2f} · {nome}",
            popup=folium.Popup(f"<b>{nome}</b><br>R$ {valor:.2f}<br>{endereco}", max_width=300),
            icon=folium.Icon(color="red" if mais_barato else "blue",
                             icon="star" if mais_barato else "info-sign"),
        ).add_to(mapa)

    sul, oeste = pontos[["latitude", "longitude"]].min()
    norte, leste = pontos[["latitude", "longitude"]].max()
    mapa.fit_bounds([[sul, oeste], [norte, leste]], max_zoom=16)
    return mapa


def para_geojson(df: pd.DataFrame, propriedades: list[str]) -> str:
    """Converte os pontos para GeoJSON (EPSG:4326), pronto para abrir no QGIS."""

    def _valor(v: Any) -> Any:
        if pd.isna(v):
            return None
        if isinstance(v, pd.Timestamp):
            return v.isoformat()
        return v.item() if hasattr(v, "item") else v

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(r["longitude"]), float(r["latitude"])]},
            "properties": {c: _valor(r[c]) for c in propriedades if c in r},
        }
        for _, r in com_coordenadas(df).iterrows()
    ]
    return json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False)


# Rampa sequencial (um só tom, do claro ao escuro): mais escuro = cesta mais cara.
RAMPA_SEQUENCIAL = ["#d6e6f8", "#a3c5ef", "#6ea2e4", "#3a7fd6", "#1f5aa6"]
SEM_DADOS = "#e4e3df"


def criar_mapa_coropletico(malha: dict, valores: pd.DataFrame, coluna: str, limites: list[float],
                           codigo_da_feicao, nomes: dict[int, str]) -> tuple[folium.Map, list[tuple[str, str]]]:
    """Mapa coroplético por município. ``valores`` tem ``codigo_ibge`` e ``coluna``.

    Devolve o mapa e a legenda [(cor, rótulo)], exibida fora do mapa pela página.
    """
    import copy

    por_codigo = valores.set_index("codigo_ibge")
    cores = RAMPA_SEQUENCIAL[-(len(limites) - 1):] if len(limites) > 1 else RAMPA_SEQUENCIAL[:1]

    def classe(v: float) -> int:
        for i in range(len(limites) - 1):
            if v <= limites[i + 1]:
                return i
        return len(limites) - 2

    geo = copy.deepcopy(malha)
    for f in geo["features"]:
        cod = codigo_da_feicao(f)
        linha = por_codigo.loc[cod] if cod in por_codigo.index else None
        valor = None if linha is None or pd.isna(linha[coluna]) else float(linha[coluna])
        f["properties"] = {
            "municipio": nomes.get(cod, str(cod)),
            "valor": f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if valor else "sem dados",
            "lojas": int(linha["com_cesta_completa"]) if linha is not None else 0,
            "_cor": cores[classe(valor)] if valor is not None else SEM_DADOS,
        }

    mapa = folium.Map(tiles="OpenStreetMap", control_scale=True)
    camada = folium.GeoJson(
        geo,
        style_function=lambda f: {"fillColor": f["properties"]["_cor"], "color": "#ffffff",
                                  "weight": 1, "fillOpacity": 0.85},
        highlight_function=lambda f: {"weight": 3, "color": "#52514e"},
        tooltip=folium.GeoJsonTooltip(fields=["municipio", "valor", "lojas"],
                                      aliases=["Município", "Cesta mediana", "Lojas com a cesta completa"]),
    ).add_to(mapa)
    mapa.fit_bounds(camada.get_bounds())

    def br(v: float) -> str:
        return f"{v:,.0f}".replace(",", ".")

    legenda = [(cores[i], f"R$ {br(limites[i])} a {br(limites[i + 1])}") for i in range(len(limites) - 1)]
    legenda.append((SEM_DADOS, "sem dados suficientes"))
    return mapa, legenda
