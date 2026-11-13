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
    at.text_input(key="t_Cerveja").input("marca inexistente").run()
    assert not at.exception and "Nenhuma oferta de **Cerveja**" in at.error[0].value
