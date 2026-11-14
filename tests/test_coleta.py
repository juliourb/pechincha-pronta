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
    for nome in ("ofertas.parquet", "lojas.parquet", "municipios.parquet", "precos.parquet", "manifesto.json", "coletas.json", "resumo.md"):
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
    rank = pan.ranking(mun)
    assert len(rank) == 3 and list(rank["cesta"]) == sorted(rank["cesta"])
    assert (rank["cesta_economica"] <= rank["cesta"]).all()
    assert pan.ranking(mun, minimo_lojas_item=99).empty
    assert any("municípios têm a cesta calculada" in f for f in pan.analise_estadual(rank))
    assert pan.correlacao_spearman(pd.Series([1, 2, 3, 4]), pd.Series([10, 8, 6, 4])) == pytest.approx(-1)
    assert "forte" in pan.descrever_correlacao(-0.8)


def test_mapa_coropletico_com_malha_minima():
    malha = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"codarea": "2704302"},
         "geometry": {"type": "Polygon", "coordinates": [[[-35.8, -9.7], [-35.6, -9.7], [-35.6, -9.5], [-35.8, -9.7]]]}},
        {"type": "Feature", "properties": {"id": "2700300"},
         "geometry": {"type": "Polygon", "coordinates": [[[-36.7, -9.8], [-36.5, -9.8], [-36.5, -9.6], [-36.7, -9.8]]]}},
    ]}
    valores = pd.DataFrame({"codigo_ibge": [2704302], "mediana": [650.0], "estabelecimentos": [12],
                            "situacao": ["completa"]})
    mapa, legenda = criar_mapa_coropletico(malha, valores, "mediana", [600, 700], col.codigo_da_feicao,
                                           {2704302: "Maceió", 2700300: "Arapiraca"})
    html = mapa.get_root().render()
    assert "Macei" in html and "sem dados" in html
    assert legenda[-1][1] == "sem dados suficientes"


def test_dias_desde_ultima_coleta_ignora_demo():
    hoje = pd.Timestamp(col.hoje())
    indice = [{"data_coleta": (hoje - pd.Timedelta(days=15)).date().isoformat()},
              {"data_coleta": (hoje - pd.Timedelta(days=2)).date().isoformat(), "demo": True}]
    assert col.dias_desde_ultima_coleta(indice) == 15
    assert col.dias_desde_ultima_coleta([]) is None


def test_coleta_envia_o_termo_e_registra_a_mensagem_de_erro():
    from economiza.api import EconomizaAPIError

    class ClienteFalso:
        def __init__(self):
            self.chamadas = []

        def pesquisar_produto(self, codigo_ibge, descricao=None, ncm=None, gtin=None, dias=7):
            self.chamadas.append((descricao, ncm))
            raise EconomizaAPIError("A API recusou a consulta. (HTTP 400: descricao obrigatoria)")

    cliente = ClienteFalso()
    ofertas, falhas = col.baixar_municipio(cliente, 2704302, 10)
    assert ofertas.empty and len(cliente.chamadas) == 15
    assert all(descricao and not ncm for descricao, ncm in cliente.chamadas)
    assert "HTTP 400" in falhas[0]


def test_reclassificar_coleta_guardada(pasta, tmp_path):
    from scripts.reclassificar_coleta import main as reclassificar_main

    raiz = tmp_path / "coletas"
    shutil.copytree(pasta, raiz / "coleta-2026-11-03")
    indice = json.loads((pasta / "coletas.json").read_text(encoding="utf-8"))
    for c in indice:
        c["demo"] = False  # simula uma coleta real
    (raiz / "coletas.json").write_text(json.dumps(indice), encoding="utf-8")
    saida = tmp_path / "reclass"
    assert reclassificar_main(["--indice", str(raiz / "coletas.json"), "--saida", str(saida),
                               "--pasta-local", str(raiz)]) == 0
    novo = json.loads((saida / "coletas.json").read_text(encoding="utf-8"))
    assert novo[0]["reclassificada_em"] and novo[0]["consultas"] == indice[0]["consultas"]
    assert (saida / "coleta-2026-11-03" / "lojas.parquet").exists()
    # categorias do Parquet não atrapalham a reclassificação
    of = col.reclassificar(pd.read_parquet(saida / "coleta-2026-11-03" / "ofertas.parquet"))
    assert (of["motivo"] == "ok").any()


def test_preparar_malha_exige_os_102_municipios():
    from economiza.municipios import MUNICIPIOS_AL
    from scripts.baixar_malha import preparar

    def quadrado(cod, chave="codarea"):
        return {"type": "Feature", "properties": {chave: str(cod)},
                "geometry": {"type": "Polygon", "coordinates": [[[-36.123456789, -9.1], [-36.0, -9.1], [-36.0, -9.0], [-36.123456789, -9.1]]]}}

    completa = {"features": [quadrado(c) for c in MUNICIPIOS_AL.values()]}
    malha = preparar(completa)
    assert len(malha["features"]) == 102
    assert malha["features"][0]["geometry"]["coordinates"][0][0][0] == -36.12346  # 5 casas
    assert {"codigo_ibge", "nome"} == set(malha["features"][0]["properties"])
    with pytest.raises(ValueError):
        preparar({"features": completa["features"][:50]})


def test_cesta_municipal_nao_exige_loja_completa_e_estima_itens_ausentes():
    from economiza import cesta_basica as cb

    def of(cnpj, item, preco):
        return {"cnpj": cnpj, "estabelecimento": cnpj, "item": item, "descricao": f"{item} KG", "preco_base": preco,
                "motivo": "ok"}

    # padaria só com pão, mercado só com arroz: nenhuma loja completa, mas o município tem os dois
    ofertas = pd.DataFrame([of("PADARIA", "Pão francês", 15.0), of("MERCADO1", "Arroz", 5.0), of("MERCADO2", "Arroz", 7.0)])
    c = cb.cesta_municipal(ofertas, ["Pão francês", "Arroz"])
    assert c["valor"] == round(6.0 * 15.0 + 3.6 * 6.0, 2) and c["itens_imputados"] == 0
    assert c["valor_economico"] < c["valor"]
    # feijão ausente: sem referência não há valor; com referência é estimado e sinalizado
    assert pd.isna(cb.cesta_municipal(ofertas, ["Pão francês", "Arroz", "Feijão"])["valor"])
    c = cb.cesta_municipal(ofertas, ["Pão francês", "Arroz", "Feijão"], referencia={"Feijão": 8.0})
    assert c["itens_imputados"] == 1 and c["itens_faltando"] == "Feijão"
    assert c["valor"] == round(6.0 * 15.0 + 3.6 * 6.0 + 4.5 * 8.0, 2)
