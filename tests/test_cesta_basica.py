import numpy as np
import pandas as pd
import pytest

from economiza import cesta_basica as cb
from economiza.demo import DemoClient

ITENS = [i.nome for i in cb.ITENS_REGIAO_2]


# ------------------------------------------------------------------ metodologia
def test_regiao_2_tem_12_itens_com_quantidades_do_decreto():
    q = {i.nome: i.quantidade for i in cb.ITENS_REGIAO_2}
    assert len(q) == 12 and "Batata" not in q
    assert q["Carne"] == 4.5 and q["Arroz"] == 3.6 and q["Farinha"] == 3.0 and q["Tomate"] == 12.0
    assert q["Café em pó"] == 0.3 and q["Banana"] == 7.5 and q["Manteiga"] == 0.75


def test_ncms_validos():
    assert all(len(n) == 8 and n.isdigit() for i in cb.ITENS_REGIAO_2 for n in i.ncms)


def test_formulas_do_dieese_batem_com_o_boletim_de_maceio():
    # Boletim DIEESE out/2026: R$ 661,69 -> 89h48m e 44,13% do salário mínimo líquido.
    assert cb.formatar_horas(cb.horas_de_trabalho(661.69)) == "89h48m"
    assert round(cb.percentual_salario_liquido(661.69), 2) == 44.13


# ------------------------------------------------------------------ embalagem e preço-base
@pytest.mark.parametrize("descricao, esperado", [
    ("ARROZ TIPO 1 MARCA 5KG", (5.0, "kg")),
    ("CAFE TORRADO 250G", (0.25, "kg")),
    ("CAFE 250 GR", (0.25, "kg")),
    ("FARINHA MANDIOCA 1,5 KG", (1.5, "kg")),
    ("OLEO DE SOJA 900ML", (0.9, "L")),
    ("LEITE INTEGRAL 1L", (1.0, "L")),
    ("LEITE INTEGRAL CX 12X1L", (12.0, "L")),
    ("LEITE INTEGRAL 1LT C/12", (12.0, "L")),
    ("FEIJAO CARIOCA T1 1KG", (1.0, "kg")),
    ("PAO FRANCES", None),
])
def test_tamanho_embalagem(descricao, esperado):
    r = cb.tamanho_embalagem(descricao)
    assert r == esperado if esperado is None else (pytest.approx(r[0]) == esperado[0] and r[1] == esperado[1])


def test_preco_base():
    arroz, banana, pao = cb.ITENS_POR_NOME["Arroz"], cb.ITENS_POR_NOME["Banana"], cb.ITENS_POR_NOME["Pão francês"]
    assert cb.preco_unidade_base(arroz, "ARROZ 5KG", "UN", 30.0) == (6.0, "ok")
    assert cb.preco_unidade_base(pao, "PAO FRANCES", "KG", 15.0) == (15.0, "ok")  # granel
    assert cb.preco_unidade_base(banana, "BANANA PRATA KG", "KG", 5.0)[0] == pytest.approx(6.0)
    assert cb.preco_unidade_base(banana, "BANANA NANICA KG", "KG", 5.0)[0] == pytest.approx(9.0)
    assert cb.preco_unidade_base(banana, "BANANA PRATA DZ", "DZ", 7.0) == (7.0, "ok")
    assert cb.preco_unidade_base(arroz, "ARROZ TIPO 1", "UN", 6.0)[0] is None
    assert cb.preco_unidade_base(arroz, "ARROZ 1L", "UN", 6.0)[1].startswith("unidade incompatível")


# ------------------------------------------------------------------ classificação
def oferta(cnpj, item, descricao, preco, um="UN", lat=-9.6):
    return {"cnpj": cnpj, "estabelecimento": f"Loja {cnpj}", "item": item, "descricao": descricao,
            "unidade_medida": um, "valor_declarado": preco, "valor_venda": preco,
            "data_venda": pd.Timestamp("2026-11-01"), "bairro": "CENTRO", "latitude": lat, "longitude": -35.7}


def test_especificacao_filtra_tipo_do_produto():
    df = pd.DataFrame([
        oferta("A", "Café em pó", "CAFE EM GRAO 500G", 30),
        oferta("A", "Café em pó", "CAFE TORRADO MOIDO 250G", 12),
        oferta("A", "Arroz", "ARROZ PARBOILIZADO 1KG", 6),
        oferta("A", "Carne", "PICANHA KG", 70, "KG"),
        oferta("A", "Carne", "CARNE BOV CX MOLE KG", 45, "KG"),
        oferta("A", "Leite", "LEITE UHT DESNATADO 1L", 5),
        oferta("A", "Banana", "BANANA DA TERRA KG", 7, "KG"),
    ])
    motivos = cb.classificar_ofertas(df).set_index("descricao")["motivo"]
    assert motivos["CAFE TORRADO MOIDO 250G"] == "ok"
    assert motivos["CARNE BOV CX MOLE KG"] == "ok"
    for d in ("CAFE EM GRAO 500G", "ARROZ PARBOILIZADO 1KG", "LEITE UHT DESNATADO 1L", "BANANA DA TERRA KG"):
        assert motivos[d] == "fora da especificação", d
    assert motivos["PICANHA KG"] == "outro produto"  # não é um dos cortes da cesta


def test_preco_atipico_descartado():
    linhas = [oferta(c, "Arroz", "ARROZ 1KG", 6.0) for c in "ABCDE"] + [oferta("F", "Arroz", "ARROZ 1KG", 0.5)]
    of = cb.classificar_ofertas(pd.DataFrame(linhas))
    assert of.loc[of.cnpj == "F", "motivo"].item() == "preço atípico"


# ------------------------------------------------------------------ cesta por loja
def ofertas_exemplo():
    linhas = [
        oferta("A", "Arroz", "ARROZ 1KG", 5.0), oferta("A", "Arroz", "ARROZ 1KG MARCA X", 7.0),
        oferta("A", "Feijão", "FEIJAO CARIOCA 1KG", 8.0),
        oferta("B", "Arroz", "ARROZ 5KG", 30.0), oferta("B", "Feijão", "FEIJAO CARIOCA 1KG", 9.0),
        oferta("C", "Arroz", "ARROZ 1KG", 4.0),  # sem feijão
    ]
    return cb.classificar_ofertas(pd.DataFrame(linhas))


def test_menor_tipica_e_maior_cesta():
    cestas = cb.cestas_por_estabelecimento(ofertas_exemplo(), ["Arroz", "Feijão"]).set_index("cnpj")
    # A: arroz min 5 / max 7 (× 3,6 kg) + feijão 8 (× 4,5 kg)
    assert cestas.loc["A", "cesta_min"] == round(5 * 3.6 + 8 * 4.5, 2)
    assert cestas.loc["A", "cesta_max"] == round(7 * 3.6 + 8 * 4.5, 2)
    assert cestas.loc["A", "cesta_tipica"] == round(6 * 3.6 + 8 * 4.5, 2)
    assert cestas.loc["B", "cesta_min"] == round(6 * 3.6 + 9 * 4.5, 2)  # 5 kg a R$ 30 = R$ 6/kg
    assert not cestas.loc["C", "completa"] and np.isnan(cestas.loc["C", "cesta_min"])
    assert cestas.loc["C", "itens_faltando"] == "Feijão"


def test_retirar_item_muda_quem_esta_completo():
    of = ofertas_exemplo()
    assert cb.cestas_por_estabelecimento(of, ["Arroz"])["completa"].all()
    m = cb.matriz_cobertura(of, ["Arroz", "Feijão"], minimo_itens=1)
    s = cb.sensibilidade(m).set_index("item")
    assert s.loc["Feijão", "ganho"] == 1 and s.loc["Feijão", "unico_item_faltando"] == 1


def test_indicadores_por_grupo_para_comparar_municipios():
    cestas = cb.cestas_por_estabelecimento(ofertas_exemplo(), ["Arroz", "Feijão"])
    cestas["municipio"] = ["MACEIO", "MACEIO", "ARAPIRACA"]
    ind = cb.indicadores(cestas, por="municipio").set_index("municipio")
    assert ind.loc["MACEIO", "com_cesta_completa"] == 2
    assert ind.loc["ARAPIRACA", "com_cesta_completa"] == 0


def test_rotulos_unicos_para_redes_com_mesmo_nome():
    df = pd.DataFrame([oferta("111111", "Arroz", "ARROZ 1KG", 5), oferta("222222", "Arroz", "ARROZ 1KG", 5)])
    df["estabelecimento"] = "REDE X"
    df.loc[1, "bairro"] = "FAROL"
    rot = cb.rotulos_estabelecimentos(df)
    assert len(set(rot.values())) == 2


def test_fluxo_completo_com_dados_demo():
    partes = []
    for item in cb.ITENS_REGIAO_2:
        for ncm in item.ncms:
            d = DemoClient().pesquisar_produto(2704302, descricao=item.termos[0])
            if not d.empty:
                partes.append(d.assign(item=item.nome))
    of = cb.classificar_ofertas(pd.concat(partes, ignore_index=True))
    cestas = cb.cestas_por_estabelecimento(of, ITENS)
    assert cestas["completa"].sum() >= 1
    comp = cb.composicao(of, cestas, ITENS)
    assert comp["participacao"].sum() == pytest.approx(100)
    frases = cb.analise_textual(cestas, comp, cb.dispersao_precos(of, ITENS),
                                cb.sensibilidade(cb.matriz_cobertura(of, ITENS, 6)), 6, 12,
                                cb.REFERENCIA_DIEESE["MACEIO"])
    assert any("DIEESE" in f for f in frases)


def test_consultas_so_pelo_termo():
    consultas = cb.consultas_api()
    assert len(consultas) == 16 and all(termo for _, termo in consultas)
    assert {i for i, _ in consultas} == set(ITENS)


@pytest.mark.parametrize("item, descricao, ncm, esperado", [
    # casos reais vistos na sondagem da API (Penedo, nov/2026)
    ("Manteiga", "Bisc Marilan Cream Cracker Manteiga 300g", "19059020", "outro produto"),
    ("Manteiga", "Marg Claybom C Sal Cr De Leite 500g", "15171000", "outro produto"),
    ("Tomate", "Ext De Tomate Elefante Tp 275g", "20029000", "outro produto"),
    ("Tomate", "Sardinha G. Da Costa C Oleo 125g", "16041310", "outro produto"),
    ("Café em pó", "Sab Palmolive Cafe e Oleo Amend 85g", "34011190", "outro produto"),
    ("Café em pó", "Cafe Pilao Sol Pouch 40g", "21011110", "fora da especificação"),
    ("Café em pó", "CAFE SANTA CLARA 250G", "09012100", "ok"),
    ("Arroz", "Mac Urbano De Arroz Z G 500g", "19021900", "outro produto"),
    ("Arroz", "Arroz Kiarroz Parb 5kg", "10063011", "fora da especificação"),
    ("Açúcar", "Bananinha Zero Acucar Rei Doces 25g", "20079990", "outro produto"),
    ("Farinha", "Farinha De Trigo Dona Benta S f 1kg", "11010010", "fora da especificação"),
    ("Farinha", "COD: 111 - FARINHA DE MANDIOCA A GRANEL KG - GRAOS", "11029000", "ok"),
    ("Farinha", "FARINHA PINHEIRO 1KG", "11062000", "ok"),          # NCM certo: basta ser farinha
    ("Farinha", "FARINHA PINHEIRO 1KG", "19019090", "fora da especificação"),  # NCM errado: exige "mandioca"
    ("Leite", "Leite Uht Molico Desn 1l", "04011010", "fora da especificação"),
    ("Leite", "Leite Uht Betania Integral C Tp 1l", "04011010", "ok"),
    ("Leite", "BL UHT CHOC BETANIA KIDS 200ML", "04039000", "outro produto"),
    ("Leite", "FRUTIGUTTI LEITE UHT INTEGRAL 1L", "04012010", "ok"),    # marca na frente, NCM certo
    ("Manteiga", "MANT CAMPONESA 200G", "04051000", "ok"),               # abreviação
    ("Açúcar", "ACUC CAETE CRISTAL 1KG", "17019900", "ok"),
    ("Pão francês", "FP PAO FRANCES A KG", "19012010", "ok"),
    ("Banana", "BANANA  PRATA KG", "07051100", "ok"),               # NCM de alface, banana de verdade
    ("Carne", "CARNE BV PATINHO", "02102000", "ok"),
    ("Carne", "CARNE BOVINA OSSO DO PATINHO KG", "02013000", "fora da especificação"),
    ("Óleo", "OLEO DE SOJA SIOL 500ML", "15071000", "ok"),
])
def test_avaliar_descricao(item, descricao, ncm, esperado):
    assert cb.avaliar_descricao(cb.ITENS_POR_NOME[item], descricao, ncm) == esperado


def test_remover_duplicadas_entre_termos():
    linha = {"item": "Carne", "cnpj": "1", "descricao": "PATINHO COXAO KG",
             "data_venda": pd.Timestamp("2026-11-01"), "valor_declarado": 40.0}
    assert len(cb.remover_duplicadas(pd.DataFrame([linha, linha]))) == 1
