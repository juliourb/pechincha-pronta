import pandas as pd

from economiza.cesta import CESTA_CHURRASCO, montar_carrinho, opcoes_por_item, total_por_estabelecimento


def linha(cnpj, item, descricao, preco, data="2026-01-10"):
    return {"cnpj": cnpj, "estabelecimento": f"Loja {cnpj}", "item": item, "descricao": descricao,
            "valor_venda": preco, "data_venda": pd.Timestamp(data),
            "latitude": -9.6, "longitude": -35.7, "bairro": "CENTRO"}


DF = pd.DataFrame([
    linha("A", "Picanha", "PICANHA FRIBOI KG", 70.0),
    linha("A", "Picanha", "PICANHA MARCA B KG", 60.0),
    linha("A", "Carvão", "CARVAO 3KG", 20.0),
    linha("B", "Picanha", "PICANHA FRIBOI KG", 65.0),
    linha("B", "Carvão", "CARVAO 3KG", 18.0),
    linha("C", "Picanha", "PICANHA FRIBOI KG", 50.0),  # não vende carvão
])


def test_ncms_tem_8_digitos():
    assert all(len(n) == 8 and n.isdigit() for ncms in CESTA_CHURRASCO.values() for n in ncms)


def test_itens_com_mesmo_ncm_nao_se_misturam():
    # Picanha e Alcatra têm o mesmo NCM; a cesta separa pela coluna "item".
    assert CESTA_CHURRASCO["Picanha"] == CESTA_CHURRASCO["Alcatra"]
    df = pd.concat([DF, pd.DataFrame([linha("A", "Alcatra", "ALCATRA KG", 40.0)])])
    carrinho = montar_carrinho(df, {"Picanha": 1, "Alcatra": 1})
    assert set(carrinho["cnpj"]) == {"A"}


def test_menor_preco_e_quantidade():
    carrinho = montar_carrinho(DF, {"Picanha": 0.5, "Carvão": 2})
    assert set(carrinho["cnpj"]) == {"A", "B"}  # C não tem a cesta completa
    a = carrinho[carrinho.cnpj == "A"].set_index("item")
    assert a.loc["Picanha", "valor_venda"] == 60.0 and a.loc["Picanha", "valor_item"] == 30.0
    assert a.loc["Carvão", "valor_item"] == 40.0


def test_escolha_de_descricao():
    carrinho = montar_carrinho(DF, {"Picanha": 1, "Carvão": 1}, {"Picanha": "PICANHA FRIBOI KG"})
    a = carrinho[(carrinho.cnpj == "A") & (carrinho.item == "Picanha")]
    assert a["valor_venda"].item() == 70.0


def test_total_ordenado_pelo_menor():
    carrinho = montar_carrinho(DF, {"Picanha": 1, "Carvão": 1})
    totais = total_por_estabelecimento(carrinho, DF)
    assert list(totais["cnpj"]) == ["A", "B"]
    assert list(totais["valor_cesta"]) == [80.0, 83.0]


def test_item_sem_dados_devolve_vazio():
    assert montar_carrinho(DF, {"Picanha": 1, "Cerveja": 1}).empty
    assert total_por_estabelecimento(montar_carrinho(DF, {"Cerveja": 1}), DF).empty


def test_opcoes_por_item():
    assert opcoes_por_item(DF)["Picanha"] == ["PICANHA FRIBOI KG", "PICANHA MARCA B KG"]
