"""Mapas (folium) e exportação GeoJSON dos resultados."""

from __future__ import annotations

import json
import math
from typing import Any

import folium
import pandas as pd


# Retângulo que envolve Alagoas, com folga. Coordenadas fora dele vêm de erro de cadastro
# na nota fiscal (na 1ª coleta real, uma loja de Junqueiro aparecia no Rio de Janeiro).
LIMITES_ALAGOAS = {"lat": (-10.7, -8.6), "lon": (-38.5, -34.9)}


def com_coordenadas(df: pd.DataFrame) -> pd.DataFrame:
    """Linhas com latitude/longitude válidas e dentro de Alagoas."""
    if df.empty or not {"latitude", "longitude"} <= set(df.columns):
        return df.iloc[0:0]
    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    validas = lat.between(*LIMITES_ALAGOAS["lat"]) & lon.between(*LIMITES_ALAGOAS["lon"])
    return df[validas]


def limites_robustos(pontos: pd.DataFrame) -> list[list[float]]:
    """Retângulo para enquadrar o mapa. Com 10 pontos ou mais, ignora os 2% mais extremos
    de cada lado, para um ponto isolado não afastar demais o zoom."""
    lat, lon = pontos["latitude"].astype(float), pontos["longitude"].astype(float)
    q = (0.02, 0.98) if len(pontos) >= 10 else (0.0, 1.0)
    return [[lat.quantile(q[0]), lon.quantile(q[0])], [lat.quantile(q[1]), lon.quantile(q[1])]]


# Enquadramento padrão: o estado de Alagoas inteiro ([[sul, oeste], [norte, leste]]).
EXTENT_ALAGOAS = [[-10.52, -38.25], [-8.80, -35.14]]
_LARGURA_PADRAO, _ALTURA_PADRAO = 700, 500  # tamanho típico do mapa na página, em pixels


def zoom_para(limites: list[list[float]], max_zoom: int = 16) -> int:
    """Zoom em que os limites cabem num mapa de tamanho típico (projeção Web Mercator)."""
    import math

    (sul, oeste), (norte, leste) = limites

    def merc(lat: float) -> float:
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    fracao_lon = max((leste - oeste) / 360, 1e-9)
    fracao_lat = max((merc(norte) - merc(sul)) / (2 * math.pi), 1e-9)
    zoom = min(math.log2(_LARGURA_PADRAO / 256 / fracao_lon), math.log2(_ALTURA_PADRAO / 256 / fracao_lat))
    return max(1, min(max_zoom, math.floor(zoom)))


def enquadrar(mapa: folium.Map, limites: list[list[float]] | None = None, max_zoom: int = 16) -> folium.Map:
    """Centraliza o mapa nos ``limites`` (padrão: Alagoas inteiro).

    O centro e o zoom já saem calculados aqui, então o mapa abre no lugar certo mesmo que o
    ajuste automático do Leaflet falhe (ele mede o mapa em pixels, e dentro de uma aba fechada
    do Streamlit o tamanho é zero). Quando o mapa fica visível ou muda de tamanho, um script
    refaz o ajuste fino.
    """
    limites = limites or EXTENT_ALAGOAS
    (sul, oeste), (norte, leste) = limites
    mapa.location = [(sul + norte) / 2, (oeste + leste) / 2]
    mapa.options["zoom"] = zoom_para(limites, max_zoom)
    mapa.options["center"] = mapa.location
    nome = mapa.get_name()
    js = f"""
    (function() {{
        var mapa = {nome}, limites = {json.dumps(limites)}, ultima = 0;
        function ajustar() {{
            var largura = mapa.getContainer().clientWidth;
            if (largura === 0 || largura === ultima) {{ return; }}
            ultima = largura;
            mapa.invalidateSize();
            mapa.fitBounds(limites, {{maxZoom: {max_zoom}, padding: [15, 15]}});
        }}
        mapa.whenReady(function() {{ setTimeout(ajustar, 200); setTimeout(ajustar, 1200); }});
        window.addEventListener("resize", ajustar);
        if (window.ResizeObserver) {{ new ResizeObserver(ajustar).observe(mapa.getContainer()); }}
        document.addEventListener("visibilitychange", ajustar);
    }})();
    """
    mapa.get_root().script.add_child(folium.Element(js))
    return mapa


def criar_mapa(df: pd.DataFrame, coluna_valor: str, coluna_nome: str = "estabelecimento") -> folium.Map | None:
    """Um marcador por estabelecimento; o(s) mais barato(s) em vermelho.

    Só entram coordenadas dentro de Alagoas, e o enquadramento ignora pontos extremos.
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

    return enquadrar(tema_escuro(mapa), limites_robustos(pontos))


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
# No tema escuro, mais claro = valor mais alto (o valor baixo se aproxima do fundo).
RAMPA_SEQUENCIAL = ["#1c4a82", "#2a66ad", "#3987e5", "#7fb2f0", "#cfe2fa"]
SEM_DADOS = "#3a3b40"

# Deixa o mapa base do OpenStreetMap escuro, sem depender de serviços que exigem chave.
_CSS_ESCURO = """<style>
.leaflet-tile-pane { filter: invert(1) hue-rotate(180deg) brightness(0.9) contrast(0.9) saturate(0.6); }
.leaflet-container { background: #0e1117; }
</style>"""


def tema_escuro(mapa: folium.Map) -> folium.Map:
    mapa.get_root().header.add_child(folium.Element(_CSS_ESCURO))
    return mapa


def criar_mapa_coropletico(malha: dict, valores: pd.DataFrame, coluna: str, limites: list[float],
                           codigo_da_feicao, nomes: dict[int, str], rotulo: str = "Cesta do município") -> tuple[folium.Map, list[tuple[str, str]]]:
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
            "lojas": int(linha["estabelecimentos"]) if linha is not None and pd.notna(linha.get("estabelecimentos")) else 0,
            "situacao": (linha.get("situacao") or "") if linha is not None else "",
            "_cor": cores[classe(valor)] if valor is not None else SEM_DADOS,
        }

    mapa = folium.Map(tiles="OpenStreetMap", control_scale=True)
    folium.GeoJson(
        geo,
        style_function=lambda f: {"fillColor": f["properties"]["_cor"], "color": "#0e1117",
                                  "weight": 1, "fillOpacity": 0.9},
        highlight_function=lambda f: {"weight": 3, "color": "#ffffff"},
        tooltip=folium.GeoJsonTooltip(fields=["municipio", "valor", "lojas", "situacao"],
                                      aliases=["Município", rotulo, "Lojas com itens da cesta", "Situação"]),
    ).add_to(mapa)
    enquadrar(tema_escuro(mapa), EXTENT_ALAGOAS, max_zoom=12)  # sempre o estado inteiro

    def br(v: float) -> str:
        return f"{v:,.0f}".replace(",", ".")

    def br2(v: float) -> str:
        return br(v) if limites[-1] >= 100 else f"{v:.2f}".replace(".", ",")

    legenda = [(cores[i], f"R$ {br2(limites[i])} a {br2(limites[i + 1])}") for i in range(len(limites) - 1)]
    legenda.append((SEM_DADOS, "sem dados suficientes"))
    return mapa, legenda
