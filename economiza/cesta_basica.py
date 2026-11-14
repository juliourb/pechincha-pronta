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
    ncms: tuple[str, ...]  # NCMs corretos do item (a nota pode trazer outro, por erro de cadastro)
    quantidade: float  # quantidade mensal do decreto, na unidade-base
    unidade: str  # "kg", "L" ou "dz"
    quantidade_texto: str  # como aparece na tabela do DIEESE
    especificacao: str
    # Regex (ou várias: todas precisam valer) que a descrição precisa conter. "^" vale para o
    # início do núcleo da descrição (sem prefixos como "COD: 12 -" ou "F ").
    exige: str | tuple[str, ...] | None = None
    proibe: str | None = None  # regex que exclui a descrição
    # Exigência extra quando o NCM da nota não é um dos corretos do item.
    exige_sem_ncm: str | None = None
    # Palavra que identifica o produto (aceita abreviações: "MANT", "ACUC"). Sem ela, a oferta é
    # "outro produto" e nem é guardada. Com o NCM correto, basta a palavra aparecer; com NCM errado
    # ela precisa abrir a descrição, porque a busca da API também devolve itens que só citam o
    # termo (biscoito "manteiga", sardinha "com tomate").
    palavra: str | None = None
    ancorar: bool = True  # False: a palavra pode vir em qualquer posição mesmo com NCM errado
    # "Cabeça" da descrição: regex das palavras que podem vir ANTES da palavra do item. Se houver
    # outra (HAMB, LING, KIT...), o produto é outra coisa feita com o item ("HAMB BOV PICANHA").
    cabeca: str | None = None
    # Grafias corretas da palavra, para aceitar erros de digitação ("MANTEGA") por semelhança.
    canonico: tuple[str, ...] = ()
    # Faixa plausível do tamanho unitário no varejo (kg ou L). Fora dela: sachê ou atacado.
    tamanho_min: float | None = None
    tamanho_max: float | None = None
    fatores_kg_para_dz: dict[str, float] = field(default_factory=dict)  # só banana
    # Termos enviados à API (sem NCM: lojas pequenas cadastram NCM errado com frequência).
    termos: tuple[str, ...] = ()
    # Peso de uma unidade, para itens vendidos "por unidade" sem peso na descrição (pão francês).
    peso_unitario_kg: float | None = None
    # Aceita número sem unidade como gramas (ex.: "CAFE SANTA CLARA 250"), se for um peso comum.
    gramas_implicitas: tuple[int, ...] = ()


# Palavras que podem vir antes do nome de um corte de carne sem mudar o que o produto é.
CABECA_CARNE = (r"CARNES?|BOVIN[AO]S?|BOV|BV|RES|RESF\w*|CONG\w*|FRESC\w*|PECA|CORTE|BIFES?|ISCAS?|MOID[AO]|"
                r"DE|DA|DO|EM|AC|ACOUGUE|KG|FRIBOI|BF|LIGHT|ESTROG\w*|\d+")
# Produtos feitos COM carne (ou outra carne): nunca são o corte. Inclui abreviações comuns.
PROCESSADOS_CARNE = (r"HAMB|LING|ALMOND|ESPET|\bKIT\b|TEMP|EMPAN|MARIN|DEFUM|CHARQUE|SALG|SUIN|\bSUI\b|PORCO|"
                     r"FRANGO|\bFGO\b|CORDEIRO|OSSO|STEAK|NUGGET|CALDO|MOLHO|RECHE|PASTEL|PIZZA|SABOR|RACAO")


# Região 2 do Decreto-Lei 399/1938 (inclui Alagoas). Ordem igual à tabela do DIEESE.
ITENS_REGIAO_2: tuple[ItemCesta, ...] = (
    ItemCesta("Carne", ("02013000", "02023000"), 4.5, "kg", "4,5 kg",
              "Carne bovina de primeira: coxão mole, coxão duro ou patinho, sem osso",
              palavra=r"PATINHO|\bCO?X(AO|\.)? ?(MOLE|DURO)|\bCHA (DE )?(DENTRO|FORA)", ancorar=False,
              cabeca=CABECA_CARNE, proibe=PROCESSADOS_CARNE, tamanho_min=0.3, tamanho_max=5,
              termos=("PATINHO", "COXAO", "CHA DENTRO", "CHA FORA")),
    ItemCesta("Leite", ("04012010", "04011010"), 6.0, "L", "6,0 L", "Leite integral UHT",
              palavra=r"LEITE?\b", exige=r"INTEGRAL|\bINT\b|\bUHT\b|LONGA VIDA",
              proibe=r"SEMI|\bDESN|\bPO\b|CONDENS|FERMENT|ACHOC|COMPOSTO|BEBIDA|ZERO|\bZR\b|LACTOSE|\bLAC\b|"
                     r"COCO|SOJA|CABRA|AVEIA|AMEND|CHOC|MORANG|CREME|DOCE|PROTEIN|KIDS|SABOR",
              canonico=("LEITE",), tamanho_min=0.5, tamanho_max=2,
              termos=("LEITE",)),
    ItemCesta("Feijão", ("07133399", "07133319"), 4.5, "kg", "4,5 kg", "Feijão carioca",
              palavra=r"FEIJ(AO)?\b", exige=r"CARIOC", proibe=r"PRONTO|TEMPERAD|COZIDO|LATA",
              canonico=("FEIJAO",), tamanho_min=0.5, tamanho_max=5,
              termos=("FEIJAO",)),
    ItemCesta("Arroz", ("10063021",), 3.6, "kg", "3,6 kg",
              "Arroz agulhinha tipo 1 (branco, não parboilizado)",
              palavra=r"ARROZ\b",
              proibe=r"PARB|INTEGRAL|\bINT\b|ARBORIO|JAPON|CATETO|NEGRO|VERMELHO|7 GRAOS|DOCE|PRONTO|TEMPERAD|"
                     r"RISOTO|CAES|\bCAO\b|CACHORRO|GATO|\bPET\b|BOBY|AMIGACO|ARROZCAO|QUIRERA|QUEBRADO",
              canonico=("ARROZ",), tamanho_min=0.5, tamanho_max=5,
              termos=("ARROZ",)),
    ItemCesta("Farinha", ("11062000",), 3.0, "kg", "3,0 kg", "Farinha de mandioca",
              palavra=r"FARI(NHA)?\b",
              proibe=r"TAPIOCA|GOMA|POLVILHO|CARIMA|PUBA|FECULA|TRIGO|ROSCA|AVEIA|MILHO|ARROZ|EMPANAR|PANKO|"
                     r"LACTEA|LINHACA|COCO|AMENDOA|CENTEIO|SOJA|BICO|BERINJ|MARACUJ|BANANA|CEVADA|QUIBE",
              exige_sem_ncm=r"MANDIOCA|\bMAND\b|D ?AGUA|AMARELA|BRANCA|\bMESA\b",
              canonico=("FARINHA",), tamanho_min=0.5, tamanho_max=5,
              termos=("FARINHA",)),
    ItemCesta("Tomate", ("07020000",), 12.0, "kg", "12,0 kg", "Tomate (comum)",
              palavra=r"TOMATES?\b",
              proibe=r"CEREJA|GRAPE|SWEET|MOLHO|EXTRATO|\bEXT\b|POLPA|SECO|PELADO|ITALIAN|ORGANIC|HOLAND",
              canonico=("TOMATE",), tamanho_min=0.3, tamanho_max=2,
              termos=("TOMATE",)),
    ItemCesta("Pão francês", ("19059090", "19012010"), 6.0, "kg", "6,0 kg", "Pão francês (carioquinha)",
              palavra=r"PAO\b", exige=r"FRANC|CARIOQ|\bSAL\b",
              proibe=r"INTEGRAL|TORRADA|\bMINI\b|PRE ?ASSAD|RECHE|DOCE|BRIOCHE|QUEIJO|SABORIZ|CONGELAD",
              peso_unitario_kg=0.05,  # pão francês padrão: 50 g
              tamanho_min=0.04, tamanho_max=1.5,
              termos=("PAO FRANCES",)),
    ItemCesta("Café em pó", ("09012100",), 0.3, "kg", "300 g", "Café torrado e moído",
              palavra=r"CAFE?\b",
              proibe=r"GRAO|^CAPS?\b|\bCAPS\b|CAPSULA|SACHE|DESCAF|SOLUV|\bSOL\b|DOLCE|GUSTO|NESCAFE|CAPP|C LEITE|"
                     r"COM LEITE|C ?/? ?LEIT|\bDESC\b|DECAF|\bREFIL\b|GRANUL|\bGRAN\b|EXPRESSO|DRIP|GELADO|PRONTO",
              gramas_implicitas=(250, 500, 1000),
              tamanho_min=0.1, tamanho_max=1,
              termos=("CAFE",)),
    ItemCesta("Banana", ("08039000", "08031000"), 7.5, "dz", "90 unid (7,5 dz)", "Banana prata ou nanica",
              palavra=r"BANANAS?\b", exige=r"PRATA|PACOVAN|NANICA|CATURRA|D.?AGUA",
              proibe=r"PASSA|DOCE|CHIPS|PALMA|CACHO|MACA|TERRA|COMPRIDA|DESIDRAT",
              # pacovan é uma variedade de banana prata
              fatores_kg_para_dz={"PRATA": 1.2, "PACOVAN": 1.2, "NANICA": 1.8, "CATURRA": 1.8, "AGUA": 1.8},
              canonico=("BANANA",),
              termos=("BANANA",)),
    ItemCesta("Açúcar", ("17019900", "17011400"), 3.0, "kg", "3,0 kg", "Açúcar cristal",
              palavra=r"ACUC(AR)?\b",
              proibe=r"DEMER|\bDEM\b|MASCAVO|REFIN|\bREF\b|CONFEIT|LIGHT|DIET|SACHE|GLAC|LIQUID|MELADO|STEVIA|ADOC|"
                     r"VEGAN|IMPALPAVEL|CUBO|COCO|ORGANIC|BAUNILHA",
              canonico=("ACUCAR",), tamanho_min=0.5, tamanho_max=5,
              termos=("ACUCAR",)),
    ItemCesta("Óleo", ("15079011", "15071000"), round(0.75 / DENSIDADE_OLEO, 3), "L", "750 g (≈ 0,815 L)",
              "Óleo de soja refinado", palavra=r"OLEO\b", exige=r"SOJA",
              proibe=r"COMPOSTO|MISTO|MOTOR|LUBRIF",
              tamanho_min=0.45, tamanho_max=2,
              termos=("OLEO SOJA",)),
    ItemCesta("Manteiga", ("04051000",), 0.75, "kg", "750 g", "Manteiga",
              palavra=r"MANT(EIGA)?\b",
              proibe=r"MARGARINA|GARRAFA|CACAU|AMENDOIM|KARITE|CORPORAL|GHEE|BISC|\bBASE\b|\bALIM|COCO|"
                     r"\bVEG|SABOR|ERVAS",
              gramas_implicitas=(200, 500),
              canonico=("MANTEIGA",), tamanho_min=0.1, tamanho_max=1,
              termos=("MANTEIGA",)),
)
ITENS_POR_NOME = {i.nome: i for i in ITENS_REGIAO_2}


def consultas_api() -> list[tuple[str, str]]:
    """(item, termo) de cada consulta à API. Uma oferta pode vir em mais de uma consulta
    (ex.: termos da carne), por isso o resultado passa por ``remover_duplicadas``."""
    return [(i.nome, termo) for i in ITENS_REGIAO_2 for termo in i.termos]


_PREFIXOS = re.compile(r"^(?:#[^ ]*#[^ ]*#\s*|COD:? ?\d+ ?-? ?|[A-Z]{1,2} (?=[A-Z]{3}))+")


def nucleo(descricao: str) -> str:
    """Descrição normalizada sem prefixos de cadastro: 'COD: 111 - FARINHA...' -> 'FARINHA...',
    'FP PAO FRANCES KG' -> 'PAO FRANCES KG'."""
    return _PREFIXOS.sub("", normalizar(descricao))


def _parecida(token: str, canonicos: tuple[str, ...]) -> bool:
    """Semelhança de texto (fuzzy) só para erros de digitação: 'MANTEGA' ~ 'MANTEIGA'.

    Exige palavras de tamanho quase igual, para 'BANANADA' não passar por 'BANANA'.
    """
    from difflib import SequenceMatcher

    return any(len(token) >= 5 and abs(len(token) - len(c)) <= 1
               and SequenceMatcher(None, token, c).ratio() >= 0.85 for c in canonicos)


def avaliar_descricao(item, descricao: str, ncm=None) -> str:
    """'ok', 'outro produto' (não é o item) ou 'fora da especificação' (é o item, de outro tipo)."""
    d = nucleo(descricao)
    palavra = getattr(item, "palavra", None)
    ncm_correto = str(ncm) in item.ncms
    if palavra:
        inicio = r"\b" if ncm_correto or not getattr(item, "ancorar", True) else "^"
        achou = re.search(f"{inicio}(?:{palavra})", d)
        if not achou:
            tokens = d.split()[: (4 if ncm_correto else 1)]
            if not any(_parecida(t, getattr(item, "canonico", ())) for t in tokens):
                return "outro produto"
        cabeca = getattr(item, "cabeca", None)
        if achou and cabeca:  # o que vem antes do nome do item precisa ser "neutro"
            antes = [re.sub(r"[^A-Z0-9]", "", t) for t in re.split(r"[\s./-]+", d[: achou.start()])]
            if any(t and not re.fullmatch(cabeca, t) for t in antes):
                return "outro produto"
    exige = item.exige if isinstance(item.exige, tuple) else ((item.exige,) if item.exige else ())
    if any(not re.search(e, d) for e in exige):
        return "fora da especificação"
    if item.proibe and re.search(item.proibe, d):
        return "fora da especificação"
    extra = getattr(item, "exige_sem_ncm", None)
    if extra and not ncm_correto and not re.search(extra, d):
        return "fora da especificação"
    return "ok"


def gtin_valido(gtin) -> bool:
    """Código de barras de verdade: 8 a 14 dígitos (as notas trazem também 'SEM GTIN')."""
    texto = str(gtin) if gtin is not None and not pd.isna(gtin) else ""
    return texto.isdigit() and 8 <= len(texto) <= 14 and int(texto) > 0


def voto_por_codigo_de_barras(dados: pd.DataFrame, minimo: int = 3, maioria: float = 0.7) -> pd.Series:
    """Consenso por código de barras: o mesmo produto recebe a mesma decisão em todas as lojas.

    Cada loja descreve o produto do seu jeito, e a regra por texto pode aceitar uma descrição e
    rejeitar outra do MESMO código de barras. Com ``minimo`` ofertas ou mais, se ``maioria`` delas
    foi rejeitada pelo texto, as demais também são; se foi aceita, as "outro produto" são resgatadas.
    Devolve os motivos corrigidos.
    """
    motivos = dados["motivo"].copy()
    if "gtin" not in dados:
        return motivos
    textual = motivos.isin(["ok", "outro produto", "fora da especificação"])
    validos = dados["gtin"].map(gtin_valido) & textual
    if not validos.any():
        return motivos
    grupo = dados.loc[validos].groupby(["item", "gtin"], observed=True)["motivo"]
    total = grupo.transform("size")
    aceitas = grupo.transform(lambda m: (m == "ok").mean())
    rejeitar = (total >= minimo) & (aceitas <= 1 - maioria) & (motivos[validos] == "ok")
    resgatar = (total >= minimo) & (aceitas >= maioria) & (motivos[validos] == "outro produto")
    motivos.loc[rejeitar[rejeitar].index] = "fora da especificação"
    motivos.loc[resgatar[resgatar].index] = "ok"
    return motivos


def remover_duplicadas(ofertas: pd.DataFrame) -> pd.DataFrame:
    chave = [c for c in ("item", "cnpj", "descricao", "data_venda", "valor_declarado") if c in ofertas]
    return ofertas.drop_duplicates(chave).reset_index(drop=True) if not ofertas.empty else ofertas


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
def normalizar_unidade(unidade_medida: str | None) -> str:
    """'KG0001', 'KG9', 'Kg' -> 'KG'; 'UN0001', 'UND9' -> 'UND' (só as letras)."""
    return re.sub(r"[^A-Z]", "", normalizar(unidade_medida))


_POR_UNIDADE = {"UN", "UND", "UNID", "UNIDADE", "PC", "PCT"}
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
    um = normalizar_unidade(unidade_medida)
    granel = _UNIDADES_GRANEL.get(um)
    tamanho = tamanho_embalagem(d)

    if item.unidade == "dz":  # banana
        if granel == "dz" or re.search(r"\bDZ\b|DUZIA", d):
            return preco, "ok"
        if granel == "kg" or re.search(r"\bKG\b", d):
            fator = next((f for chave, f in item.fatores_kg_para_dz.items() if chave in d), None)
            if fator is None:
                return None, "banana sem tipo (prata/nanica)"
            return preco * fator, "ok"
        if (um in _POR_UNIDADE or re.search(r"\bUN(D|ID|IDADE)?\b", d)) and tamanho is None:
            return preco * 12, "ok"  # vendida por unidade: uma dúzia = 12 unidades
        return None, "unidade de venda desconhecida"

    if granel == item.unidade:  # vendido a granel: o preço já é por kg ou por litro
        return preco, "ok"
    if tamanho is None and item.peso_unitario_kg and um in _POR_UNIDADE and not re.search(r"\bKG\b", d):
        return preco / item.peso_unitario_kg, "ok"  # ex.: pão francês por unidade (50 g)
    if tamanho is None and item.gramas_implicitas:
        numero = re.search(r"\b(\d{3,4})\s*$", d)
        if numero and int(numero.group(1)) in item.gramas_implicitas:
            tamanho = (int(numero.group(1)) / 1000, "kg")
    if tamanho is None:
        return None, "tamanho da embalagem não encontrado"
    quantidade, unidade = tamanho
    if unidade != item.unidade:
        return None, f"unidade incompatível ({unidade})"
    return preco / quantidade, "ok"


# --------------------------------------------------------------------------------------
# 2. Classificação das ofertas
# --------------------------------------------------------------------------------------
def classificar_ofertas(df: pd.DataFrame, itens: dict | None = None,
                        ignorar_especificacao: bool = False) -> pd.DataFrame:
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
    situacoes = [("ok" if ignorar_especificacao else avaliar_descricao(itens[l.item], l.descricao, getattr(l, "ncm", None)))
                 for l in dados.itertuples(index=False)]
    dados["motivo"] = situacoes
    if not ignorar_especificacao:
        dados["motivo"] = voto_por_codigo_de_barras(dados)
    tamanhos = dados["descricao"].map(embalagem)
    dados["tamanho_unitario"] = tamanhos.map(lambda e: e[1] if e else np.nan)
    for linha, situacao, tamanho in zip(dados.itertuples(index=False), dados["motivo"], dados["tamanho_unitario"]):
        item = itens[linha.item]
        if situacao != "ok":
            precos.append(None); motivos.append(situacao)
            continue
        minimo, maximo = getattr(item, "tamanho_min", None), getattr(item, "tamanho_max", None)
        if pd.notna(tamanho) and ((minimo and tamanho < minimo) or (maximo and tamanho > maximo)):
            precos.append(None); motivos.append("embalagem fora do varejo")
            continue
        p, motivo = preco_unidade_base(item, nucleo(linha.descricao), linha.unidade_medida, linha.preco)
        precos.append(p); motivos.append(motivo)
    dados["preco_base"] = pd.to_numeric(pd.Series(precos, index=dados.index), errors="coerce")
    dados["motivo"] = motivos

    # Preços atípicos (erro de cadastro ou de leitura do tamanho), item a item.
    ok = dados["motivo"] == "ok"
    mediana = dados["item"].map(dados[ok].groupby("item")["preco_base"].median())
    atipico = ok & ((dados["preco_base"] < mediana / FATOR_ATIPICO) | (dados["preco_base"] > mediana * FATOR_ATIPICO))
    dados.loc[atipico, "motivo"] = "preço atípico"
    dados.loc[dados["motivo"] != "ok", "preco_base"] = np.nan
    # Mantém também as demais colunas da API (gtin, cep...): a coleta estadual as guarda para
    # permitir refazer a classificação no futuro sem consultar a API de novo.
    dados = dados.drop(columns="preco")
    return dados[[c for c in colunas if c in dados] + [c for c in dados.columns if c not in colunas]]


# --------------------------------------------------------------------------------------
# 3. Cesta por estabelecimento
# --------------------------------------------------------------------------------------
def precos_por_estabelecimento(ofertas: pd.DataFrame, itens: list[str]) -> pd.DataFrame:
    """Menor, mediano e maior preço-base de cada item em cada estabelecimento."""
    validas = ofertas[(ofertas["motivo"] == "ok") & ofertas["item"].isin(itens)]
    # Parquet devolve colunas categóricas; texto simples evita erros no agrupamento.
    validas = validas.assign(item=validas["item"].astype(str), cnpj=validas["cnpj"].astype(str))
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


# --------------------------------------------------------------------------------------
# 5. Cesta do município (cada item comprado onde houver)
# --------------------------------------------------------------------------------------
MAX_IMPUTADOS = 3  # até quantos itens sem preço local podem ser estimados pelo preço de referência


def precos_municipio(ofertas: pd.DataFrame, itens: list[str] | None = None) -> pd.DataFrame:
    """Preço de cada item no município: mediana e "preço baixo" (percentil 10, menos sensível
    a erros de cadastro que o mínimo) entre as lojas, usando a opção mais barata de cada loja,
    e em quantas lojas o item foi encontrado."""
    itens = itens or [i.nome for i in ITENS_REGIAO_2]
    por_loja = precos_por_estabelecimento(ofertas, itens)
    if por_loja.empty:
        return pd.DataFrame(columns=["item", "lojas", "preco_mediano", "preco_menor"])
    t = (por_loja.groupby("item")["preco_min"]
         .agg(lojas="count", preco_mediano="median",
              preco_menor=lambda s: s.quantile(0.10)).reset_index())
    return t


def cesta_municipal(ofertas: pd.DataFrame, itens: list[str] | None = None,
                    referencia: dict[str, float] | None = None) -> dict:
    """Cesta do município, sem exigir que uma única loja venda tudo.

    É a lógica do DIEESE: o preço de cada item é o típico do lugar (aqui, a mediana entre as
    lojas), e a cesta é a soma das quantidades do decreto × esses preços. Assim o pão pode vir
    da padaria e a carne do açougue.

    - ``valor``: cesta com o preço mediano de cada item;
    - ``valor_economico``: comprando cada item onde ele é barato (percentil 10 das lojas);
    - itens sem nenhum preço local são estimados pelo preço de ``referencia`` (ex.: mediana
      do estado) quando são no máximo ``MAX_IMPUTADOS``; acima disso a cesta fica sem valor.
    """
    itens = itens or [i.nome for i in ITENS_REGIAO_2]
    precos = precos_municipio(ofertas, itens).set_index("item")
    faltando = [i for i in itens if i not in precos.index]
    resultado = {"itens_com_preco": len(itens) - len(faltando), "itens_faltando": ", ".join(faltando),
                 "itens_imputados": 0, "valor": np.nan, "valor_economico": np.nan,
                 "lojas_por_item_min": int(precos["lojas"].min()) if len(precos) and not faltando else 0,
                 "lojas_por_item_mediana": float(precos["lojas"].median()) if len(precos) else 0.0}
    referencia = referencia or {}
    if len(faltando) > MAX_IMPUTADOS or any(i not in referencia for i in faltando):
        return resultado
    total = garimpado = 0.0
    for nome in itens:
        qtd = ITENS_POR_NOME[nome].quantidade
        if nome in precos.index:
            total += qtd * precos.loc[nome, "preco_mediano"]
            garimpado += qtd * precos.loc[nome, "preco_menor"]
        else:
            total += qtd * referencia[nome]
            garimpado += qtd * referencia[nome]
    resultado.update(valor=round(total, 2), valor_economico=round(garimpado, 2), itens_imputados=len(faltando))
    return resultado


def precos_de_referencia(ofertas: pd.DataFrame) -> dict[str, float]:
    """Mediana estadual do preço de cada item (entre todas as lojas da coleta)."""
    t = precos_municipio(ofertas)
    return dict(zip(t["item"], t["preco_mediano"]))
