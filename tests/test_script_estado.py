import json

import pandas as pd

from scripts.cesta_basica_estado import main


def test_script_gera_indicadores_por_municipio(tmp_path):
    assert main(["--municipios", "Maceió", "Arapiraca", "--saida", str(tmp_path), "--pausa", "0"]) == 0
    mun = pd.read_csv(tmp_path / "municipios.csv")
    assert set(mun["municipio"]) == {"MACEIO", "ARAPIRACA"}
    assert set(mun["codigo_ibge"]) == {2704302, 2700300}
    gj = json.loads((tmp_path / "lojas.geojson").read_text(encoding="utf-8"))
    assert gj["features"]
    # segunda execução usa o cache
    assert main(["--municipios", "Maceió", "--saida", str(tmp_path), "--pausa", "0"]) == 0
