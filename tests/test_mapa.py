import json

import pandas as pd

from economiza.mapa import com_coordenadas, criar_mapa, para_geojson

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


def test_coordenadas_fora_de_alagoas_sao_ignoradas_e_enquadramento_robusto():
    from economiza.mapa import limites_robustos

    pontos = pd.DataFrame({"estabelecimento": [f"L{i}" for i in range(21)], "valor": range(21),
                           "latitude": [-9.6 - i * 0.001 for i in range(20)] + [-21.8],   # uma no RJ
                           "longitude": [-35.7 - i * 0.001 for i in range(20)] + [-41.4]})
    assert len(com_coordenadas(pontos)) == 20
    mapa = criar_mapa(pontos, "valor")
    html = mapa.get_root().render()
    assert "-21.8" not in html and "invalidateSize" in html  # reenquadra quando a aba aparece
    (sul, oeste), (norte, leste) = limites_robustos(com_coordenadas(pontos))
    assert -9.63 < sul < norte < -9.59


def test_enquadramento_padrao_e_alagoas_com_centro_e_zoom_definidos():
    import re

    import folium

    from economiza.mapa import EXTENT_ALAGOAS, enquadrar, zoom_para

    html = enquadrar(folium.Map()).get_root().render()
    lat, lon = map(float, re.search(r"center: \[([-\d.]+), ([-\d.]+)\]", html).groups())
    assert -10.0 < lat < -9.3 and -37.2 < lon < -36.2          # centro do estado, não [0, 0]
    assert '"zoom": 8' in html and zoom_para(EXTENT_ALAGOAS) == 8
    assert zoom_para([[-9.70, -35.86], [-9.49, -35.57]]) == 11  # uma cidade pede mais zoom
    # mapa de pontos: centro nos pontos, sem depender do ajuste automático do navegador
    html = criar_mapa(DF, "valor").get_root().render()
    lat, lon = map(float, re.search(r"center: \[([-\d.]+), ([-\d.]+)\]", html).groups())
    assert -9.75 < lat < -9.55 and -35.85 < lon < -35.65
