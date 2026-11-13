import json

import pandas as pd

from economiza.mapa import criar_mapa, para_geojson

DF = pd.DataFrame({"estabelecimento": ["A", "B", "C"], "valor": [5.0, 6.0, 7.0],
                   "latitude": [-9.6, -9.7, None], "longitude": [-35.7, -35.8, None],
                   "data": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])})


def test_mapa_ignora_sem_coordenada():
    html = criar_mapa(DF, "valor").get_root().render()
    assert html.count("L.marker(") == 2 and "red" in html


def test_mapa_sem_pontos():
    assert criar_mapa(DF.iloc[2:], "valor") is None


def test_geojson_lon_lat_e_serializavel():
    gj = json.loads(para_geojson(DF, ["estabelecimento", "valor", "data"]))
    assert len(gj["features"]) == 2
    assert gj["features"][0]["geometry"]["coordinates"] == [-35.7, -9.6]
    assert gj["features"][0]["properties"]["data"].startswith("2026-01-01")
