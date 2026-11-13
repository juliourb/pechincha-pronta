import pandas as pd
import pytest

from economiza.cesta import (CESTA_CHURRASCO, classificar_churrasco, filtrar_ofertas, montar_carrinho,
                             total_por_estabelecimento)


def oferta(cnpj, item, descricao, preco, um="UN", ncm=None, data="2026-11-10"):
    return {"cnpj": cnpj, "estabelecimento": f"Loja {cnpj}", "item": item, "descricao": descricao,
            "ncm": ncm or CESTA_CHURRASCO[item].ncms[0], "unidade_medida": um,
            "valor_declarado": preco, "valor_venda": preco, "data_venda": pd.Timestamp(data),
            "latitude": -9.6, "longitude": -35.7, "bairro": "CENTRO"}


OFERTAS = classificar_churrasco(pd.DataFrame([
    oferta("A", "Picanha", "PICANHA BOVINA KG", 70.0, "KG", "02013000"),
    oferta("A", "Picanha", "PICANHA CONGELADA KG", 60.0, "KG", "02023000"),
    oferta("A", "Picanha", "PICANHA SUINA KG", 30.0, "KG"),
    oferta("A", "Cerveja", "CERVEJA MARCA X LATA 350ML", 3.50),          # R$ 10,00/L
    oferta("A", "Cerveja", "CERVEJA MARCA Y LATA 350ML C/12", 36.00),    # R$ 8,57/L
    oferta("A", "Cerveja", "CERVEJA MARCA Z GARRAFA 600ML", 4.80),       # R$ 8,00/L
    oferta("A", "Cerveja", "CERVEJA MARCA X LONG NECK 330ML", 5.94),     # R$ 18,00/L
    oferta("A", "Cerveja", "DOSE CERVEJA", 2.00),                        # sem tamanho
    oferta("A", "Carvão", "CARVAO 3KG", 18.0),
    oferta("B", "Picanha", "PICANHA BOVINA KG", 65.0, "KG", "02013000"),
    oferta("B", "Cerveja", "CERVEJA MARCA X LATA 350ML", 3.15),          # R$ 9,00/L
    oferta("B", "Carvão", "CARVAO 5KG", 25.0),                            # R$ 5,00/kg
    oferta("C", "Picanha", "PICANHA BOVINA KG", 50.0, "KG", "02013000"),  # não vende carvão
    oferta("C", "Cerveja", "CERVEJA MARCA X LATA 350ML", 3.00),
]))


def test_ncms_tem_8_digitos():
    assert all(len(n) == 8 and n.isdigit() for i in CESTA_CHURRASCO.values() for n in i.ncms)


def test_classificacao_descarta_item_errado_e_sem_tamanho():
    motivos = OFERTAS.set_index("descricao")["motivo"]
    assert motivos["PICANHA SUINA KG"] == "fora da especificação"
    assert motivos["DOSE CERVEJA"] == "tamanho da embalagem não encontrado"
    assert motivos["CERVEJA MARCA Y LATA 350ML C/12"] == "ok"


def test_preco_por_litro_compara_embalagens():
    p = OFERTAS.set_index("descricao")["preco_base"]
    assert p["CERVEJA MARCA Y LATA 350ML C/12"] == pytest.approx(36 / 4.2)
    assert p["CERVEJA MARCA Z GARRAFA 600ML"] == pytest.approx(8.0)


@pytest.mark.parametrize("subfiltro, esperado", [
    ("Lata 350 ml", {"CERVEJA MARCA X LATA 350ML", "CERVEJA MARCA Y LATA 350ML C/12"}),
    ("Long neck", {"CERVEJA MARCA X LONG NECK 330ML"}),
    ("Garrafa 600 ml", {"CERVEJA MARCA Z GARRAFA 600ML"}),
])
def test_subfiltro_formato_da_cerveja(subfiltro, esperado):
    f = filtrar_ofertas(OFERTAS, {"Cerveja": {"subfiltro": subfiltro, "texto": ""}})
    assert set(f.loc[(f.item == "Cerveja") & (f.cnpj == "A"), "descricao"]) == esperado


def test_subfiltro_congelada_usa_o_ncm():
    f = filtrar_ofertas(OFERTAS, {"Picanha": {"subfiltro": "Congelada", "texto": ""}})
    assert set(f.loc[f.item == "Picanha", "descricao"]) == {"PICANHA CONGELADA KG"}


def test_filtro_por_marca_ignora_caixa_e_acento():
    f = filtrar_ofertas(OFERTAS, {"Cerveja": {"subfiltro": None, "texto": "marca z"}})
    assert set(f.loc[f.item == "Cerveja", "descricao"]) == {"CERVEJA MARCA Z GARRAFA 600ML"}
    # o filtro de um item não mexe nos outros
    assert (f.item == "Picanha").sum() == 4


def test_carrinho_usa_o_mais_barato_por_unidade_e_so_lojas_completas():
    car = montar_carrinho(filtrar_ofertas(OFERTAS), {"Picanha": 1.5, "Cerveja": 4.2, "Carvão": 3})
    assert set(car["cnpj"]) == {"A", "B"}  # C não vende carvão
    a = car[car.cnpj == "A"].set_index("item")
    assert a.loc["Picanha", "valor_item"] == 90.0                 # 1,5 kg × R$ 60 (congelada)
    assert a.loc["Cerveja", "descricao"] == "CERVEJA MARCA Z GARRAFA 600ML"
    assert a.loc["Cerveja", "valor_item"] == pytest.approx(33.6)  # 4,2 L × R$ 8/L
    totais = total_por_estabelecimento(car, OFERTAS)
    # A: 90 + 33,60 + 18 = 141,60   B: 1,5 × 65 + 4,2 × 9 + 3 × 5 = 150,30
    assert list(totais["cnpj"]) == ["A", "B"]
    assert list(totais["valor_cesta"]) == [141.6, 150.3]


def test_sem_dados_devolve_vazio():
    assert montar_carrinho(filtrar_ofertas(OFERTAS), {"Picanha": 1, "Farofa": 1}).empty
    vazio = montar_carrinho(OFERTAS.iloc[0:0], {"Picanha": 1})
    assert total_por_estabelecimento(vazio, OFERTAS).empty
