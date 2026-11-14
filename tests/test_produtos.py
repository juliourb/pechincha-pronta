"""O motor de produtos é um só para todas as páginas."""

import pandas as pd

from economiza import cesta, cesta_basica, produtos


def linha(cnpj, item, descricao, preco, gtin="SEM GTIN", um="UN"):
    return {"cnpj": cnpj, "estabelecimento": cnpj, "item": item, "descricao": descricao, "gtin": gtin,
            "ncm": "22030000", "unidade_medida": um, "valor_declarado": preco, "valor_venda": preco,
            "data_venda": pd.Timestamp("2026-11-10")}


def test_as_duas_cestas_usam_o_mesmo_motor_e_as_mesmas_listas():
    assert issubclass(cesta_basica.ItemCesta, produtos.RegrasProduto)
    assert issubclass(cesta.ItemChurrasco, produtos.RegrasProduto)
    assert cesta_basica.avaliar_descricao is produtos.avaliar_descricao
    assert cesta_basica.ITENS_POR_NOME["Carne"].cabeca is produtos.CABECA_CARNE
    assert cesta.CESTA_CHURRASCO["Picanha"].cabeca is produtos.CABECA_CARNE
    assert produtos.PROCESSADOS_CARNE in cesta.CESTA_CHURRASCO["Picanha"].proibe


def test_modulo_novo_so_precisa_declarar_os_itens():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class ItemNovo(produtos.RegrasProduto):
        nome: str
        ncms: tuple
        unidade: str

    itens = {"Refrigerante": ItemNovo("Refrigerante", ("22021000",), "L", palavra=r"REFRI", proibe=r"ZERO",
                                      tamanho_min=0.2, tamanho_max=3)}
    df = pd.DataFrame([linha("A", "Refrigerante", "REFRIGERANTE COLA 2L", 8.0),
                       linha("B", "Refrigerante", "REFRIG COLA ZERO 2L", 8.0),
                       linha("C", "Refrigerante", "COPO REFRIGERANTE 300ML", 5.0)])
    df["ncm"] = ["22021000", "22021000", "39241000"]
    motivos = produtos.classificar_ofertas(df, itens).set_index("cnpj")
    assert motivos.loc["A", "motivo"] == "ok" and motivos.loc["A", "preco_base"] == 4.0
    assert motivos.loc["B", "motivo"] == "fora da especificação"
    assert motivos.loc["C", "motivo"] == "outro produto"


def test_catalogo_e_filtro_por_marca():
    df = pd.DataFrame([
        linha("A", "Cerveja", "CERVEJA SKOL LATA 350ML", 3.0, "7891149101900"),
        linha("B", "Cerveja", "CERV SKOL PILSEN LT 350ML", 3.2, "7891149101900"),   # mesmo código, outra descrição
        linha("B", "Cerveja", "CERVEJA SKOL LONG NECK 330ML", 5.0),
        linha("C", "Cerveja", "CERVEJA BRAHMA LATA 350ML", 3.1),
        linha("C", "Picanha", "PICANHA SKOL KG", 60.0, um="KG"),                   # outro item: não é afetado
    ])
    of = cesta.classificar_churrasco(df)
    cat = produtos.catalogo(of, "Cerveja", "L")
    assert len(cat) == 3 and cat.iloc[0]["lojas"] == 2
    so_skol = produtos.catalogo(of, "Cerveja", "L", marca="skol")
    assert len(so_skol) == 2 and so_skol["nome"].str.contains("SKOL").all()
    assert len(produtos.catalogo(of, "Cerveja", "L", marca="lata skol")) == 1   # várias palavras, qualquer ordem
    f = produtos.filtrar_produtos(of, "Cerveja", marca="Skol")
    assert set(f.loc[f.item == "Cerveja", "cnpj"]) == {"A", "B"} and (f.item == "Picanha").sum() == 1
    f = produtos.filtrar_produtos(of, "Cerveja", produtos=["gtin:7891149101900"], marca="skol")
    assert len(f[f.item == "Cerveja"]) == 2
    assert len(produtos.filtrar_produtos(of, "Cerveja")) == len(of)                # sem filtro, nada muda
