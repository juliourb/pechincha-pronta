import pytest

from economiza.municipios import MUNICIPIOS_AL, codigo_ibge, normalizar


def test_102_municipios_com_codigo_de_alagoas():
    assert len(MUNICIPIOS_AL) == 102
    assert all(str(c).startswith("27") and len(str(c)) == 7 for c in MUNICIPIOS_AL.values())
    assert len(set(MUNICIPIOS_AL.values())) == 102


def test_codigo_ignora_acento_e_caixa():
    assert codigo_ibge(" maceió ") == 2704302
    assert codigo_ibge("Olho d'Água das Flores") == 2705705


def test_municipio_inexistente_levanta_erro():
    with pytest.raises(ValueError):
        codigo_ibge("Recife")


def test_normalizar_valores_nao_texto():
    assert normalizar(None) == ""
    assert normalizar(float("nan")) == ""


def test_nome_oficial_com_acentos():
    from economiza.municipios import MUNICIPIOS_AL, nome_oficial

    assert nome_oficial("SAO JOSE DA TAPERA") == "São José da Tapera"
    assert nome_oficial("OLHO D'AGUA DAS FLORES") == "Olho d'Água das Flores"
    assert nome_oficial("COITE DO NOIA") == "Coité do Nóia"
    assert nome_oficial("PALMEIRA DOS INDIOS") == "Palmeira dos Índios"
    assert nome_oficial("maceió") == "Maceió"
    assert len({nome_oficial(n) for n in MUNICIPIOS_AL}) == 102
