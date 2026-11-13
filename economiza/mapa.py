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
