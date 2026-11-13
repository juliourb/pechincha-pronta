"""Cesta básica (Decreto-Lei 399/1938, Região 2) a partir das notas fiscais.

Fontes da metodologia:
- DIEESE, *Metodologia da Pesquisa Nacional da Cesta Básica de Alimentos* (ago/2025):
  quantidades mensais por região; Alagoas está na Região 2 (12 itens, sem batata).
- Especificação dos produtos (mesmo documento e boletins mensais do DIEESE): carne bovina
  de primeira (coxão mole, coxão duro e patinho, sem osso), leite integral UHT, feijão
  carioca, arroz agulhinha, farinha de mandioca (Norte/Nordeste), tomate, pão francês,
  café em pó, banana prata ou nanica, açúcar cristal, óleo de soja e manteiga.
- Banana vendida por kg: preço da dúzia = preço do kg × 1,2 (prata) ou × 1,8 (nanica).

Como a marca não importa, cada item é buscado pelo(s) código(s) NCM e depois filtrado
pela descrição (palavras obrigatórias e proibidas), para manter o tipo do produto.
O preço de cada oferta é convertido para a unidade-base do item (R$/kg, R$/L ou R$/dúzia)
lendo o tamanho da embalagem na descrição.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .municipios import normalizar

SALARIO_MINIMO = 1621.00  # Decreto 12.797/2025, vigente em 2026
JORNADA_MENSAL_HORAS = 220  # Constituição de 1988, usada pelo DIEESE
DESCONTO_PREVIDENCIA = 0.075  # salário mínimo líquido = SM × (1 - 7,5%)
DENSIDADE_OLEO = 0.92  # kg/L do óleo de soja: converte os 750 g do decreto para litros
FATOR_ATIPICO = 3.0  # preço-base < mediana/3 ou > mediana×3 é descartado como atípico

# Referência oficial para comparação: DIEESE, boletim de outubro de 2026 (Maceió).
REFERENCIA_DIEESE = {"MACEIO": {"valor": 661.69, "periodo": "out/2026"}}


@dataclass(frozen=True)
class ItemCesta:
    nome: str
    ncms: tuple[str, ...]
    quantidade: float  # quantidade mensal do decreto, na unidade-base
    unidade: str  # "kg", "L" ou "dz"
    quantidade_texto: str  # como aparece na tabela do DIEESE
    especificacao: str
    exige: str | None = None  # regex que a descrição precisa conter
    proibe: str | None = None  # regex que exclui a descrição
    fatores_kg_para_dz: dict[str, float] = field(default_factory=dict)  # só banana


# Região 2 do Decreto-Lei 399/1938 (inclui Alagoas). Ordem igual à tabela do DIEESE.
ITENS_REGIAO_2: tuple[ItemCesta, ...] = (
    ItemCesta("Carne", ("02013000", "02023000"), 4.5, "kg", "4,5 kg",
              "Carne bovina de primeira: coxão mole, coxão duro ou patinho, sem osso",
              exige=r"PATINHO|\bCO?X(AO|\.)? ?(MOLE|DURO)|\bCHA (DE )?(DENTRO|FORA)"),
    ItemCesta("Leite", ("04012010",), 6.0, "L", "6,0 L", "Leite integral UHT",
              exige=r"INTEGRAL", proibe=r"SEMI|DESNAT|\bPO\b|CONDENS|FERMENT|ACHOC"),
    ItemCesta("Feijão", ("07133399", "07133319"), 4.5, "kg", "4,5 kg", "Feijão carioca",
              exige=r"CARIOC"),
    ItemCesta("Arroz", ("10063021",), 3.6, "kg", "3,6 kg",
              "Arroz agulhinha tipo 1 (branco, não parboilizado)",
              proibe=r"PARBO|INTEGRAL|ARBORIO|JAPON|CATETO|NEGRO|VERMELHO|7 GRAOS"),
    ItemCesta("Farinha", ("11062000",), 3.0, "kg", "3,0 kg", "Farinha de mandioca",
              proibe=r"TAPIOCA|GOMA|POLVILHO|CARIMA|PUBA|FECULA"),
    ItemCesta("Tomate", ("07020000",), 12.0, "kg", "12,0 kg", "Tomate (comum)",
              proibe=r"CEREJA|GRAPE|SWEET|MOLHO|EXTRATO|POLPA|SECO"),
    ItemCesta("Pão francês", ("19059090",), 6.0, "kg", "6,0 kg", "Pão francês (carioquinha)",
              exige=r"\bPAO\b.*(FRANC|CARIOQ|\bSAL\b)|CARIOQUINHA"),
    ItemCesta("Café em pó", ("09012100",), 0.3, "kg", "300 g", "Café torrado e moído",
              proibe=r"GRAO|CAPSULA|SACHE|DESCAF|SOLUVEL"),
    ItemCesta("Banana", ("08039000",), 7.5, "dz", "90 unid (7,5 dz)", "Banana prata ou nanica",
              exige=r"PRATA|NANICA|CATURRA|D.?AGUA",
              fatores_kg_para_dz={"PRATA": 1.2, "NANICA": 1.8, "CATURRA": 1.8, "AGUA": 1.8}),
    ItemCesta("Açúcar", ("17019900", "17011400"), 3.0, "kg", "3,0 kg", "Açúcar cristal",
              exige=r"CRISTAL"),
    ItemCesta("Óleo", ("15079011",), round(0.75 / DENSIDADE_OLEO, 3), "L", "750 g (≈ 0,815 L)",
              "Óleo de soja refinado", exige=r"SOJA"),
    ItemCesta("Manteiga", ("04051000",), 0.75, "kg", "750 g", "Manteiga",
              proibe=r"MARGARINA|GARRAFA|CACAU|AMENDOIM"),
)
ITENS_POR_NOME = {i.nome: i for i in ITENS_REGIAO_2}


# --------------------------------------------------------------------------------------
# 1. Tamanho da embalagem e preço na unidade-base
# --------------------------------------------------------------------------------------
_UNIDADES = {
    "KG": ("kg", 1.0), "KGS": ("kg", 1.0), "KILO": ("kg", 1.0), "KILOS": ("kg", 1.0),
    "QUILO": ("kg", 1.0), "G": ("kg", 0.001), "GR": ("kg", 0.001), "GRS": ("kg", 0.001),
    "GRAMAS": ("kg", 0.001), "L": ("L", 1.0), "LT": ("L", 1.0), "LTS": ("L", 1.0),
    "LITRO": ("L", 1.0), "LITROS": ("L", 1.0), "ML": ("L", 0.001),
}
_NUM = r"(\d+(?:[.,]\d+)?)"
_RE_TAMANHO = re.compile(_NUM + r"\s*(" + "|".join(sorted(_UNIDADES, key=len, reverse=True)) + r")\b")
_RE_MULTI = re.compile(r"(\d+)\s*[X\*]\s*" + _NUM + r"\s*(" + "|".join(sorted(_UNIDADES, key=len, reverse=True)) + r")\b")
_RE_CAIXA = re.compile(r"\b(?:C/|CX\s*C/?|COM)\s*(\d+)\s*(?:UN|UND|UNID)?\b")
_UNIDADES_GRANEL = {"KG": "kg", "KGS": "kg", "KILO": "kg", "QUILO": "kg", "L": "L", "LT": "L", "LTS": "L", "DZ": "dz", "DUZIA": "dz"}


def _num(txt: str) -> float:
    return float(txt.replace(",", "."))


def embalagem(descricao: str) -> tuple[float, float, str] | None:
    """Lê a embalagem na descrição e devolve ``(total, unitario, unidade)``.

    '5KG' -> (5, 5, 'kg'); 'CERVEJA LATA 350ML C/12' -> (4,2, 0,35, 'L'); '12X1L' -> (12, 1, 'L').
    O tamanho unitário serve para filtrar formatos (lata de 350 ml, garrafa de 600 ml...).
    """
    d = normalizar(descricao)
    m = _RE_MULTI.search(d)
    if m:
        unidade, fator = _UNIDADES[m.group(3)]
        unitario = _num(m.group(2)) * fator
        return int(m.group(1)) * unitario, unitario, unidade
    tamanhos = _RE_TAMANHO.findall(d)
    if not tamanhos:
        return None
    valor, sigla = tamanhos[-1]  # o último costuma ser o peso/volume da embalagem
    unidade, fator = _UNIDADES[sigla]
    unitario = _num(valor) * fator
    caixa = _RE_CAIXA.search(d)
    total = unitario * int(caixa.group(1)) if caixa else unitario
    return (total, unitario, unidade) if total > 0 else None


def tamanho_embalagem(descricao: str) -> tuple[float, str] | None:
    """Conteúdo total da embalagem: '5KG' -> (5, 'kg'), '12X1L' -> (12, 'L').

    Devolve ``None`` quando não encontra um tamanho (a oferta vai para o diagnóstico).
    """
    e = embalagem(descricao)
    return (e[0], e[2]) if e else None


def preco_unidade_base(item: ItemCesta, descricao: str, unidade_medida: str | None,
                       preco: float) -> tuple[float | None, str]:
    """Converte o preço da oferta para R$ por unidade-base do item.

    Devolve ``(preco_base, motivo)``; ``preco_base`` é ``None`` quando não dá para converter.
    """
    if pd.isna(preco) or preco <= 0:
        return None, "sem preço"
    d = normalizar(descricao)
    um = normalizar(unidade_medida)
    granel = _UNIDADES_GRANEL.get(um)

    if item.unidade == "dz":  # banana
        if granel == "dz" or re.search(r"\bDZ\b|DUZIA", d):
            return preco, "ok"
        if granel == "kg" or re.search(r"\bKG\b", d):
            fator = next((f for chave, f in item.fatores_kg_para_dz.items() if chave in d), None)
            if fator is None:
                return None, "banana sem tipo (prata/nanica)"
            return preco * fator, "ok"
        return None, "unidade de venda desconhecida"

    if granel == item.unidade:  # vendido a granel: o preço já é por kg ou por litro
        return preco, "ok"
    tamanho = tamanho_embalagem(d)
    if tamanho is None:
        return None, "tamanho da embalagem não encontrado"
    quantidade, unidade = tamanho
    if unidade != item.unidade:
        return None, f"unidade incompatível ({unidade})"
    return preco / quantidade, "ok"


# --------------------------------------------------------------------------------------
# 2. Classificação das ofertas
# --------------------------------------------------------------------------------------
def classificar_ofertas(df: pd.DataFrame, itens: dict | None = None) -> pd.DataFrame:
    """Recebe as ofertas da API (com a coluna ``item``) e devolve uma linha por oferta com
    ``preco_base`` (R$ por kg, L ou dúzia), ``tamanho_unitario`` e ``motivo``
    ('ok' ou por que foi descartada).

    ``itens`` mapeia nome -> definição do item (padrão: a cesta básica). A cesta de
    churrasco usa a mesma função com os seus próprios itens.
    """
    itens = itens or ITENS_POR_NOME
    colunas = ["item", "cnpj", "estabelecimento", "descricao", "ncm", "unidade_medida", "valor_declarado",
               "valor_venda", "data_venda", "preco_base", "tamanho_unitario", "motivo"]
    if df.empty:
        return pd.DataFrame(columns=colunas)
    dados = df.copy()
    for col in ("unidade_medida", "valor_venda", "valor_declarado"):
        if col not in dados:
            dados[col] = pd.NA
    # Preço de referência: o valor unitário declarado na nota ("preço de prateleira").
    dados["preco"] = dados["valor_declarado"].fillna(dados["valor_venda"])
    precos, motivos = [], []
    for linha in dados.itertuples(index=False):
        item = itens[linha.item]
        desc = normalizar(linha.descricao)
        if item.exige and not re.search(item.exige, desc):
            precos.append(None); motivos.append("fora da especificação")
            continue
        if item.proibe and re.search(item.proibe, desc):
            precos.append(None); motivos.append("fora da especificação")
            continue
        p, motivo = preco_unidade_base(item, desc, linha.unidade_medida, linha.preco)
        precos.append(p); motivos.append(motivo)
    dados["preco_base"] = pd.to_numeric(pd.Series(precos, index=dados.index), errors="coerce")
    tamanhos = dados["descricao"].map(embalagem)
    dados["tamanho_unitario"] = tamanhos.map(lambda e: e[1] if e else np.nan)
    dados["motivo"] = motivos

    # Preços atípicos (erro de cadastro ou de leitura do tamanho), item a item.
    ok = dados["motivo"] == "ok"
    mediana = dados["item"].map(dados[ok].groupby("item")["preco_base"].median())
    atipico = ok & ((dados["preco_base"] < mediana / FATOR_ATIPICO) | (dados["preco_base"] > mediana * FATOR_ATIPICO))
    dados.loc[atipico, "motivo"] = "preço atípico"
    dados.loc[dados["motivo"] != "ok", "preco_base"] = np.nan
    return dados[[c for c in colunas if c in dados] + [c for c in ("bairro", "logradouro", "numero", "latitude", "longitude", "municipio", "codigo_ibge") if c in dados]]


# --------------------------------------------------------------------------------------
# 3. Cesta por estabelecimento
# --------------------------------------------------------------------------------------
def precos_por_estabelecimento(ofertas: pd.DataFrame, itens: list[str]) -> pd.DataFrame:
    """Menor, mediano e maior preço-base de cada item em cada estabelecimento."""
    validas = ofertas[(ofertas["motivo"] == "ok") & ofertas["item"].isin(itens)]
    return (
        validas.groupby(["cnpj", "item"])
        .agg(preco_min=("preco_base", "min"), preco_mediano=("preco_base", "median"),
             preco_max=("preco_base", "max"), ofertas=("descricao", "nunique"))
        .reset_index()
    )


def cestas_por_estabelecimento(ofertas: pd.DataFrame, itens: list[str] | None = None) -> pd.DataFrame:
    """Uma linha por estabelecimento, com a cobertura e o valor da cesta.

    - ``cesta_min``: soma, item a item, da opção mais barata da loja (× quantidade do decreto);
    - ``cesta_tipica``: idem com o preço mediano; ``cesta_max``: com a opção mais cara.
    Os valores só existem quando a loja tem **todos** os itens (``completa``).
    """
    itens = itens or [i.nome for i in ITENS_REGIAO_2]
    precos = precos_por_estabelecimento(ofertas, itens)
    colunas_local = ["cnpj", "estabelecimento", "bairro", "logradouro", "numero",
                     "municipio", "codigo_ibge", "latitude", "longitude"]
    if precos.empty:
        return pd.DataFrame(columns=[*colunas_local, "n_itens", "completa", "itens_faltando",
                                     "cesta_min", "cesta_tipica", "cesta_max", "amplitude"])
    qtd = precos["item"].map(lambda n: ITENS_POR_NOME[n].quantidade)
    for col in ("min", "mediano", "max"):
        precos[f"gasto_{col}"] = precos[f"preco_{col}"] * qtd

    resumo = precos.groupby("cnpj").agg(
        n_itens=("item", "nunique"), cesta_min=("gasto_min", "sum"),
        cesta_tipica=("gasto_mediano", "sum"), cesta_max=("gasto_max", "sum"),
        _itens=("item", lambda s: set(s)),
    )
    resumo["completa"] = resumo["n_itens"] == len(itens)
    resumo["itens_faltando"] = resumo["_itens"].map(lambda s: ", ".join(i for i in itens if i not in s))
    for col in ("cesta_min", "cesta_tipica", "cesta_max"):
        resumo.loc[~resumo["completa"], col] = np.nan
        resumo[col] = resumo[col].round(2)
    resumo["amplitude"] = (resumo["cesta_max"] - resumo["cesta_min"]).round(2)

    disponiveis = [c for c in colunas_local if c in ofertas.columns]
    locais = (ofertas[disponiveis].sort_values("latitude", na_position="last")
              .drop_duplicates("cnpj").set_index("cnpj"))
    resultado = resumo.drop(columns="_itens").join(locais, how="left").reset_index()
    return resultado.sort_values(["completa", "cesta_min", "n_itens"],
                                 ascending=[False, True, False]).reset_index(drop=True)


# --------------------------------------------------------------------------------------
# 4. Análises: indicadores, composição, cobertura e sensibilidade
# --------------------------------------------------------------------------------------
def brl(valor: float) -> str:
    """R$ no formato brasileiro: 1234.5 -> 'R$ 1.234,50'."""
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def numero_br(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def horas_de_trabalho(valor: float, salario_minimo: float = SALARIO_MINIMO) -> float:
    """Horas que quem ganha um salário mínimo trabalha para comprar a cesta (fórmula do DIEESE)."""
    return valor * JORNADA_MENSAL_HORAS / salario_minimo


def formatar_horas(horas: float) -> str:
    h, m = divmod(round(horas * 60), 60)
    return f"{h}h{m:02d}m"


def percentual_salario_liquido(valor: float, salario_minimo: float = SALARIO_MINIMO) -> float:
    return 100 * valor / (salario_minimo * (1 - DESCONTO_PREVIDENCIA))


def indicadores(cestas: pd.DataFrame, por: str | None = None) -> pd.DataFrame:
    """Estatísticas descritivas da cesta mínima entre os estabelecimentos completos.

    Com ``por="municipio"`` (ou "bairro") calcula um conjunto por grupo: é a base para
    comparar municípios num levantamento do estado inteiro.
    """
    def _resumo(g: pd.DataFrame) -> pd.Series:
        completas = g.loc[g["completa"], "cesta_min"]
        mediana = completas.median() if len(completas) else np.nan
        return pd.Series({
            "estabelecimentos": len(g),
            "com_cesta_completa": int(g["completa"].sum()),
            "pct_completos": 100 * g["completa"].mean() if len(g) else np.nan,
            "menor_cesta": completas.min(), "p25": completas.quantile(0.25),
            "mediana": mediana, "media": completas.mean(), "p75": completas.quantile(0.75),
            "maior_cesta": completas.max(),
            "diferenca_maior_menor": completas.max() - completas.min(),
            "horas_trabalho_mediana": horas_de_trabalho(mediana) if pd.notna(mediana) else np.nan,
            "pct_salario_liquido_mediana": percentual_salario_liquido(mediana) if pd.notna(mediana) else np.nan,
        })

    if por is None:
        return _resumo(cestas).to_frame().T
    return cestas.groupby(por).apply(_resumo, include_groups=False).reset_index()


def composicao(ofertas: pd.DataFrame, cestas: pd.DataFrame, itens: list[str]) -> pd.DataFrame:
    """Peso de cada item na cesta mediana (gasto mediano entre os estabelecimentos completos)."""
    completos = cestas.loc[cestas["completa"], "cnpj"]
    precos = precos_por_estabelecimento(ofertas[ofertas["cnpj"].isin(completos)], itens)
    if precos.empty:
        return pd.DataFrame(columns=["item", "quantidade", "preco_base_mediano", "gasto", "participacao"])
    tabela = precos.groupby("item")["preco_min"].median().rename("preco_base_mediano").reset_index()
    tabela["quantidade"] = tabela["item"].map(lambda n: ITENS_POR_NOME[n].quantidade_texto)
    tabela["unidade"] = tabela["item"].map(lambda n: ITENS_POR_NOME[n].unidade)
    tabela["gasto"] = tabela["preco_base_mediano"] * tabela["item"].map(lambda n: ITENS_POR_NOME[n].quantidade)
    tabela["participacao"] = 100 * tabela["gasto"] / tabela["gasto"].sum()
    return tabela.sort_values("gasto", ascending=False).reset_index(drop=True)


def dispersao_precos(ofertas: pd.DataFrame, itens: list[str]) -> pd.DataFrame:
    """Para cada item: menor, mediano e maior preço-base entre estabelecimentos (usando a
    opção mais barata de cada loja) e quantas vezes o maior é o menor."""
    precos = precos_por_estabelecimento(ofertas, itens)
    if precos.empty:
        return pd.DataFrame(columns=["item", "unidade", "estabelecimentos", "menor", "mediano", "maior", "razao_maior_menor"])
    t = precos.groupby("item")["preco_min"].agg(estabelecimentos="count", menor="min", mediano="median", maior="max").reset_index()
    t["unidade"] = t["item"].map(lambda n: ITENS_POR_NOME[n].unidade)
    t["razao_maior_menor"] = t["maior"] / t["menor"]
    return t.sort_values("razao_maior_menor", ascending=False).reset_index(drop=True)


def rotulos_estabelecimentos(ofertas: pd.DataFrame) -> dict[str, str]:
    """Nome legível e único por CNPJ (redes com o mesmo nome ganham o bairro ou o CNPJ)."""
    lojas = ofertas.drop_duplicates("cnpj").set_index("cnpj")
    nomes = lojas["estabelecimento"].fillna("Sem nome").astype(str)
    if "bairro" in lojas:
        repetido = nomes.duplicated(keep=False)
        nomes[repetido] = nomes[repetido] + " · " + lojas.loc[repetido, "bairro"].fillna("").astype(str).str.title()
    repetido = nomes.duplicated(keep=False)
    nomes[repetido] = nomes[repetido] + " · " + nomes[repetido].index.astype(str).str[-6:]
    return nomes.to_dict()


def matriz_cobertura(ofertas: pd.DataFrame, itens: list[str], minimo_itens: int) -> pd.DataFrame:
    """Matriz estabelecimento × item (True = vende). Considera só lojas com ``minimo_itens``
    ou mais, para focar em mercados (e não em padarias que só vendem pão, por exemplo)."""
    validas = ofertas[(ofertas["motivo"] == "ok") & ofertas["item"].isin(itens)]
    if validas.empty:
        return pd.DataFrame(columns=itens)
    m = pd.crosstab(validas["cnpj"].map(rotulos_estabelecimentos(ofertas)), validas["item"]) > 0
    m = m.reindex(columns=itens, fill_value=False)
    m = m[m.sum(axis=1) >= minimo_itens]
    return m.loc[m.sum(axis=1).sort_values(ascending=False).index]


def sensibilidade(matriz: pd.DataFrame) -> pd.DataFrame:
    """Para cada item: % de lojas que o vendem, quantas lojas ficam sem a cesta só por causa
    dele (faltava apenas ele) e quantas teriam a cesta completa se ele saísse."""
    if matriz.empty:
        return pd.DataFrame(columns=["item", "cobertura_pct", "unico_item_faltando", "completas_sem_o_item"])
    completas_hoje = int(matriz.all(axis=1).sum())
    linhas = []
    for item in matriz.columns:
        outros = matriz.drop(columns=item)
        linhas.append({
            "item": item,
            "cobertura_pct": 100 * matriz[item].mean(),
            "unico_item_faltando": int((~matriz[item] & outros.all(axis=1)).sum()),
            "completas_sem_o_item": int(outros.all(axis=1).sum()),
            "ganho": int(outros.all(axis=1).sum()) - completas_hoje,
        })
    return pd.DataFrame(linhas).sort_values(["ganho", "cobertura_pct"], ascending=[False, True]).reset_index(drop=True)


def resumo_diagnostico(ofertas: pd.DataFrame) -> pd.DataFrame:
    """Quantas ofertas foram aceitas ou descartadas, por item e motivo."""
    if ofertas.empty:
        return pd.DataFrame(columns=["item", "motivo", "ofertas"])
    return (ofertas.groupby(["item", "motivo"]).size().rename("ofertas").reset_index()
            .sort_values(["item", "ofertas"], ascending=[True, False]))


def analise_textual(cestas: pd.DataFrame, comp: pd.DataFrame, disp: pd.DataFrame,
                    sens: pd.DataFrame, minimo_itens: int, n_itens: int,
                    referencia: dict | None = None) -> list[str]:
    """Uma pequena análise em frases, gerada a partir dos resultados."""
    r = brl
    frases = []
    analisadas = cestas[cestas["n_itens"] >= minimo_itens]
    completas = cestas[cestas["completa"]].sort_values("cesta_min")
    frases.append(
        f"Dos **{len(analisadas)}** estabelecimentos que vendem ao menos {minimo_itens} dos "
        f"{n_itens} itens, **{len(completas)}** têm a cesta completa."
    )
    if completas.empty:
        return frases
    mais_barata, mais_cara = completas.iloc[0], completas.iloc[-1]
    mediana = completas["cesta_min"].median()
    frases.append(
        f"A cesta mais barata está em **{mais_barata['estabelecimento']}**: {r(mais_barata['cesta_min'])}, "
        f"{100 * (1 - mais_barata['cesta_min'] / mediana):.0f}% abaixo da mediana ({r(mediana)})."
    )
    if len(completas) > 1:
        diferenca = mais_cara["cesta_min"] - mais_barata["cesta_min"]
        frases.append(
            f"Entre a loja mais barata e a mais cara, a diferença é de **{r(diferenca)}** por mês, "
            f"o equivalente a {formatar_horas(horas_de_trabalho(diferenca))} de trabalho para quem ganha um salário mínimo."
        )
    amplitude = completas["amplitude"].median()
    frases.append(
        f"Dentro de uma mesma loja, escolher sempre a opção mais cara em vez da mais barata "
        f"encarece a cesta em {r(amplitude)} (mediana entre as lojas): a escolha da marca também pesa."
    )
    if not comp.empty and len(comp) > 1:
        a, b = comp.iloc[0], comp.iloc[1]
        frases.append(
            f"Os itens que mais pesam são **{a['item']}** ({a['participacao']:.0f}% da cesta) e "
            f"**{b['item']}** ({b['participacao']:.0f}%)."
        )
    if not disp.empty:
        d = disp.iloc[0]
        frases.append(
            f"O item com maior variação de preço entre lojas é **{d['item']}**: a loja mais cara cobra "
            f"{100 * (d['razao_maior_menor'] - 1):.0f}% a mais que a mais barata. É onde comparar preços rende mais."
        )
    if not sens.empty and sens["ganho"].max() > 0:
        maximo = sens["ganho"].max()
        lideres = sens.loc[sens["ganho"] == maximo, "item"].tolist()
        if len(lideres) == 1:
            frases.append(
                f"O item que mais impede a cesta completa é **{lideres[0]}**: sem ele, mais "
                f"{int(maximo)} loja(s) teriam a cesta completa."
            )
        else:
            frases.append(
                f"Nenhum item sozinho explica a falta de cestas completas: {len(lideres)} itens "
                f"({', '.join(lideres)}) empatam, cada um faltando em {int(maximo)} loja(s) que só não tinham ele."
            )
    if referencia and len(completas):
        dif = 100 * (mediana / referencia["valor"] - 1)
        frases.append(
            f"Comparação: o DIEESE calculou {r(referencia['valor'])} para Maceió ({referencia['periodo']}). "
            f"A mediana daqui está {abs(dif):.0f}% {'acima' if dif > 0 else 'abaixo'}. As metodologias "
            "diferem (o DIEESE faz a média de marcas em lojas amostradas; aqui é a opção mais barata de cada loja)."
        )
    return frases
