"""Testes de ponta a ponta das páginas, em modo demonstração (sem rede)."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parents[1]

T = 60


def test_inicio_abre_em_modo_demo():
    at = AppTest.from_file(str(RAIZ / "Inicio.py"), default_timeout=T).run()
    assert not at.exception
    assert "Modo demonstração" in at.warning[0].value


def test_combustivel_consulta():
    at = AppTest.from_file(str(RAIZ / "pages/1_Combustivel.py"), default_timeout=T).run()
    at.button[0].click().run()
    assert not at.exception
    assert at.metric[0].value == "12"
    assert len(at.dataframe) == 1


def test_combustivel_bairro_sem_resultado():
    at = AppTest.from_file(str(RAIZ / "pages/1_Combustivel.py"), default_timeout=T).run()
    at.text_input[0].input("bairro que nao existe")
    at.button[0].click().run()
    assert not at.exception and "Nenhuma nota" in at.info[0].value


def test_churrasco_consulta_e_refina():
    at = AppTest.from_file(str(RAIZ / "pages/2_Churrasco.py"), default_timeout=T).run()
    at.button[0].click().run()
    assert not at.exception
    assert "Melhor opção" in at.success[0].value
    total_antes = at.metric[1].value
    at.number_input(key="q_Picanha").set_value(2.0).run()
    assert not at.exception and at.metric[1].value != total_antes


def test_cesta_basica_calcula_e_permite_retirar_item():
    at = AppTest.from_file(str(RAIZ / "pages/3_Cesta_basica.py"), default_timeout=T).run()
    at.button[0].click().run()
    assert not at.exception
    completas_antes = at.metric[0].value
    assert "Análise" in " ".join(m.value for m in at.markdown)
    at.multiselect[0].unselect("Pão francês").run()
    assert not at.exception
    assert at.metric[0].value != completas_antes


def test_churrasco_subfiltro_de_formato():
    at = AppTest.from_file(str(RAIZ / "pages/2_Churrasco.py"), default_timeout=T).run()
    at.button[0].click().run()
    total_antes = at.metric[1].value
    at.selectbox(key="s_Cerveja").set_value("Long neck").run()
    assert not at.exception
    assert at.metric[1].value != total_antes  # long neck é mais cara por litro
    # o catálogo lista os produtos long neck encontrados; escolher um restringe a cesta
    catalogo_cerveja = at.multiselect(key="p_Cerveja_Long neck_")
    assert catalogo_cerveja.options and all("LONG NECK" in o for o in catalogo_cerveja.options)
    catalogo_cerveja.select(catalogo_cerveja.options[0]).run()
    assert not at.exception


def test_churrasco_filtro_por_marca():
    at = AppTest.from_file(str(RAIZ / "pages/2_Churrasco.py"), default_timeout=T).run()
    at.button[0].click().run()
    todos = at.multiselect(key="p_Cerveja_Qualquer_").options
    at.text_input(key="m_Cerveja_Qualquer").input("pilsen").run()
    assert not at.exception
    so_marca = at.multiselect(key="p_Cerveja_Qualquer_pilsen").options
    assert 0 < len(so_marca) < len(todos) and all("PILSEN" in o for o in so_marca)
    # só a marca, sem marcar produtos: a cesta usa apenas ofertas dessa marca
    at.text_input(key="m_Cerveja_Qualquer").input("marca inexistente").run()
    assert not at.exception and "Nenhuma oferta de **Cerveja**" in at.error[0].value


def test_cesta_basica_usa_o_mesmo_filtro_de_produtos():
    at = AppTest.from_file(str(RAIZ / "pages/3_Cesta_basica.py"), default_timeout=T).run()
    at.button[0].click().run()
    antes = at.metric[0].value
    at.selectbox(key="item_filtro").set_value("Café em pó").run()
    at.text_input(key="m_cb_Café em pó").input("500g").run()
    assert not at.exception
    assert any("Restrições ativas" in i.value for i in at.info)
    assert at.metric[0].value != antes  # a cesta foi recalculada só com o café de 500 g


def test_panorama_le_coletas_locais(tmp_path, monkeypatch):
    import shutil

    from scripts.coleta_estadual import main

    saida = tmp_path / "saida"
    assert main(["--municipios", "MACEIO", "ARAPIRACA", "PENEDO", "--saida", str(saida), "--pausa", "0",
                 "--data", "2026-11-03"]) == 0
    raiz = tmp_path / "coletas"
    shutil.copytree(saida, raiz / "coleta-2026-11-03")
    shutil.copy(saida / "coletas.json", raiz / "coletas.json")
    monkeypatch.setenv("PECHINCHA_COLETAS_DIR", str(raiz))
    at = AppTest.from_file(str(RAIZ / "pages/4_Panorama.py"), default_timeout=T).run()
    assert not at.exception
    assert at.metric[0].value == "3 de 102"
    assert "Análise" in " ".join(m.value for m in at.markdown)
