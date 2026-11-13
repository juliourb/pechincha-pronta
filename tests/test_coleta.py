import json
import shutil

import pandas as pd
import pytest

from economiza import coleta as col
from economiza import panorama as pan
from economiza.mapa import criar_mapa_coropletico
from scripts.coleta_estadual import main

MUNICIPIOS = ["MACEIO", "ARAPIRACA", "PENEDO"]


@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    saida = tmp_path_factory.mktemp("coleta")
    assert main(["--municipios", *MUNICIPIOS, "--saida", str(saida), "--pausa", "0", "--data", "2026-11-03"]) == 0
    return saida


def test_arquivos_e_manifesto(pasta):
    for nome in ("ofertas.parquet", "lojas.parquet", "municipios.parquet", "manifesto.json", "coletas.json", "resumo.md"):
        assert (pasta / nome).exists(), nome
    m = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    assert m["tag"] == "coleta-2026-11-03" and m["consultas"] == 3 * 15 and m["demo"] is True
    assert m["arquivos"]["ofertas"]["linhas"] == len(pd.read_parquet(pasta / "ofertas.parquet"))
    assert m["arquivos"]["ofertas"]["bytes"] == (pasta / "ofertas.parquet").stat().st_size
    assert m["estado"]["municipios_com_dados"] == 3


def test_ofertas_guardam_dados_brutos_para_reclassificar(pasta):
    of = pd.read_parquet(pasta / "ofertas.parquet")
    assert list(of.columns) == col.COLUNAS_OFERTAS
    assert set(of["municipio"].astype(str)) == set(MUNICIPIOS)
    assert of["gtin"].notna().any() and (of["data_coleta"] == "2026-11-03").all()


def test_indice_acumula_historico(pasta, tmp_path):
    saida = tmp_path / "segunda"
    assert main(["--municipios", "MACEIO", "--saida", str(saida), "--pausa", "0", "--data", "2026-11-13",
                 "--indice-anterior", str(pasta / "coletas.json")]) == 0
    indice = json.loads((saida / "coletas.json").read_text(encoding="utf-8"))
    assert [c["data_coleta"] for c in indice] == ["2026-11-03", "2026-11-13"]
    proj = col.projecao_anual(indice)
    assert proj["coletas"] == 2 and proj["mb_por_ano"] == pytest.approx(proj["mb_por_coleta"] * 36.5)


def test_exigir_token_impede_publicar_dados_ficticios(tmp_path):
    assert main(["--municipios", "MACEIO", "--saida", str(tmp_path), "--exigir-token"]) == 2


def test_leitura_local(pasta, tmp_path):
    raiz = tmp_path / "coletas"
    shutil.copytree(pasta, raiz / "coleta-2026-11-03")
    shutil.copy(pasta / "coletas.json", raiz / "coletas.json")
    indice = col.ler_indice(raiz)
    lojas = col.ler_tabela(indice[0], "lojas", raiz)
    assert len(lojas) > 0 and "cesta_min" in lojas


def test_ranking_e_correlacao(pasta):
    mun = pd.read_parquet(pasta / "municipios.parquet")
    rank = pan.ranking(mun, 1)
    assert list(rank["mediana"]) == sorted(rank["mediana"])
    assert pan.correlacao_spearman(pd.Series([1, 2, 3, 4]), pd.Series([10, 8, 6, 4])) == pytest.approx(-1)
    assert "forte" in pan.descrever_correlacao(-0.8)


def test_mapa_coropletico_com_malha_minima():
    malha = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"codarea": "2704302"},
         "geometry": {"type": "Polygon", "coordinates": [[[-35.8, -9.7], [-35.6, -9.7], [-35.6, -9.5], [-35.8, -9.7]]]}},
        {"type": "Feature", "properties": {"id": "2700300"},
         "geometry": {"type": "Polygon", "coordinates": [[[-36.7, -9.8], [-36.5, -9.8], [-36.5, -9.6], [-36.7, -9.8]]]}},
    ]}
    valores = pd.DataFrame({"codigo_ibge": [2704302], "mediana": [650.0], "com_cesta_completa": [12]})
    mapa, legenda = criar_mapa_coropletico(malha, valores, "mediana", [600, 700], col.codigo_da_feicao,
                                           {2704302: "Maceió", 2700300: "Arapiraca"})
    html = mapa.get_root().render()
    assert "Macei" in html and "sem dados" in html
    assert legenda[-1][1] == "sem dados suficientes"
