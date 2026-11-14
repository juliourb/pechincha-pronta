"""Motor de identificação de produtos, comum a todas as páginas.

Qualquer módulo novo (outra cesta, outra lista de compras) deve usar este motor em vez de criar
regras próprias. O caminho é sempre o mesmo:

1. Definir os itens herdando de ``RegrasProduto`` (palavra, exclusões, faixa de embalagem...);
2. ``classificar_ofertas(ofertas, itens)``: decide, oferta a oferta, se é o item, e converte o
   preço para R$ por kg, litro ou dúzia;
3. ``catalogo(ofertas, item, unidade)``: lista os produtos encontrados (nome, tamanho, lojas, preço);
4. ``filtrar_produtos(ofertas, item, produtos, marca)``: restringe a produtos ou a uma marca.

As listas compartilhadas (``CABECA_CARNE``, ``PROCESSADOS_CARNE``) também ficam aqui, para que
uma correção valha para todas as páginas. Metodologia: docs/CESTA_BASICA.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .municipios import normalizar

FATOR_ATIPICO = 3.0  # preço-base < mediana/3 ou > mediana×3 é descartado como atípico


@dataclass(frozen=True, kw_only=True)
class RegrasProduto:
    """Regras de identificação de um produto. Os itens de cada página herdam desta classe e
    acrescentam o que é próprio delas (quantidade da cesta, subfiltros...).

    Toda subclasse precisa ter ``nome``, ``ncms`` e ``unidade`` ("kg", "L" ou "dz").
    """

    # Palavra que identifica o produto (aceita abreviações: "MANT", "ACUC"). Sem ela, a oferta é
    # "outro produto". Com o NCM correto, basta a palavra aparecer; com NCM errado ela precisa
    # abrir a descrição, porque a busca da API também devolve itens que só citam o termo
    # (biscoito "manteiga", sardinha "com tomate").
    palavra: str | None = None
    ancorar: bool = True  # False: a palavra pode vir em qualquer posição mesmo com NCM errado
    # "Cabeça" da descrição: regex das palavras que podem vir ANTES da palavra do item. Se houver
    # outra (HAMB, LING, KIT...), o produto é outra coisa feita com o item ("HAMB BOV PICANHA").
    cabeca: str | None = None
    # Grafias corretas da palavra, para aceitar erros de digitação ("MANTEGA") por semelhança.
    canonico: tuple[str, ...] = ()
    # Regex (ou várias: todas precisam valer) que a descrição precisa conter.
    exige: str | tuple[str, ...] | None = None
    proibe: str | None = None  # regex que exclui a descrição
    exige_sem_ncm: str | None = None  # exigência extra quando o NCM da nota não é o do item
    # Faixa plausível do tamanho unitário no varejo (kg ou L). Fora dela: sachê ou atacado.
    tamanho_min: float | None = None
    tamanho_max: float | None = None
    # Peso de uma unidade, para itens vendidos "por unidade" sem peso na descrição (pão francês).
    peso_unitario_kg: float | None = None
    # Aceita número sem unidade como gramas (ex.: "CAFE SANTA CLARA 250"), se for um peso comum.
    gramas_implicitas: tuple[int, ...] = ()
    fatores_kg_para_dz: dict[str, float] = field(default_factory=dict)  # só banana


# --------------------------------------------------------------------------------------
# Listas compartilhadas
# --------------------------------------------------------------------------------------
# Palavras que podem vir antes do nome de um corte de carne sem mudar o que o produto é.
CABECA_CARNE = (r"CARNES?|BOVIN[AO]S?|BOV|BV|RES|RESF\w*|CONG\w*|FRESC\w*|PECA|CORTE|BIFES?|ISCAS?|MOID[AO]|"
                r"DE|DA|DO|EM|AC|ACOUGUE|KG|FRIBOI|BF|LIGHT|ESTROG\w*|\d+")
# Produtos feitos COM carne (ou outra carne): nunca são o corte. Inclui abreviações comuns.
PROCESSADOS_CARNE = (r"HAMB|LING|ALMOND|ESPET|\bKIT\b|TEMP|EMPAN|MARIN|DEFUM|CHARQUE|SALG|SUIN|\bSUI\b|PORCO|"
                     r"FRANGO|\bFGO\b|CORDEIRO|OSSO|STEAK|NUGGET|CALDO|MOLHO|RECHE|PASTEL|PIZZA|SABOR|RACAO")



# --------------------------------------------------------------------------------------
# A oferta é o item? (texto, NCM e código de barras)
# --------------------------------------------------------------------------------------
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
# Tamanho da embalagem e preço na unidade-base
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


def preco_unidade_base(item: RegrasProduto, descricao: str, unidade_medida: str | None,
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
# Classificação das ofertas
# --------------------------------------------------------------------------------------
def classificar_ofertas(df: pd.DataFrame, itens: dict[str, RegrasProduto],
                        ignorar_especificacao: bool = False) -> pd.DataFrame:
    """Recebe as ofertas da API (com a coluna ``item``) e devolve uma linha por oferta com
    ``preco_base`` (R$ por kg, L ou dúzia), ``tamanho_unitario`` e ``motivo``
    ('ok' ou por que foi descartada).

    ``itens`` mapeia nome -> definição do item (padrão: a cesta básica). A cesta de
    churrasco usa a mesma função com os seus próprios itens.
    """
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
# Catálogo e filtro de produtos (iguais em todas as páginas)
# --------------------------------------------------------------------------------------
def chave_produto(gtin, descricao: str) -> str:
    """Identifica o produto: o código de barras quando existe; senão, a descrição."""
    return f"gtin:{gtin}" if gtin_valido(gtin) else f"desc:{normalizar(descricao)}"


def com_chave_produto(ofertas: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta a coluna ``produto`` (a chave usada no catálogo e no filtro)."""
    ofertas = ofertas.copy()
    if "gtin" not in ofertas:
        ofertas["gtin"] = pd.NA
    ofertas["produto"] = [chave_produto(g, d) for g, d in zip(ofertas["gtin"], ofertas["descricao"])]
    return ofertas


def tamanho_legivel(tamanho: float, unidade: str) -> str:
    """0.35 L -> '350 ml'; 5 kg -> '5 kg'; sem tamanho -> 'a granel'."""
    if pd.isna(tamanho):
        return "a granel"
    if tamanho < 1:
        return f"{tamanho * 1000:.0f} {'ml' if unidade == 'L' else 'g'}"
    return f"{tamanho:g} {unidade}".replace(".", ",")


def _contem_marca(descricoes: pd.Series, marca: str | None) -> pd.Series:
    """True onde a descrição contém todas as palavras digitadas (sem acento, qualquer ordem)."""
    palavras = normalizar(marca).split()
    texto = descricoes.map(normalizar)
    ok = pd.Series(True, index=descricoes.index)
    for palavra in palavras:
        ok &= texto.str.contains(r"\b" + re.escape(palavra), regex=True)  # início de palavra
    return ok


def filtrar_produtos(ofertas: pd.DataFrame, item: str, produtos: list[str] | None = None,
                     marca: str | None = None) -> pd.DataFrame:
    """Restringe as ofertas de ``item`` a produtos do catálogo e/ou a uma marca (texto livre).

    As ofertas dos outros itens não são alteradas. ``marca`` vale para qualquer palavra da
    descrição: "skol", "skol lata", "friboi".
    """
    if not produtos and not normalizar(marca):
        return ofertas
    do_item = ofertas["item"] == item
    manter = pd.Series(True, index=ofertas.index)
    linhas = ofertas[do_item]
    ok = _contem_marca(linhas["descricao"], marca)
    if produtos:
        ok &= linhas["produto"].isin(produtos)
    manter[linhas.index] = ok
    return ofertas[manter]


def catalogo(ofertas: pd.DataFrame, item: str, unidade: str, marca: str | None = None) -> pd.DataFrame:
    """Produtos encontrados para um item: nome, tamanho, em quantas lojas e o menor preço.

    O mesmo código de barras aparece com descrições diferentes em cada loja; o catálogo junta
    tudo num produto só e usa a descrição mais comum como nome. ``marca`` filtra pelo texto.
    """
    colunas = ["produto", "nome", "tamanho", "lojas", "menor_preco", "menor_preco_base", "rotulo"]
    validas = ofertas[(ofertas["motivo"] == "ok") & (ofertas["item"] == item)]
    if validas.empty:
        return pd.DataFrame(columns=colunas)
    if "produto" not in validas:
        validas = com_chave_produto(validas)
    validas = validas.assign(_nome=validas["descricao"].map(normalizar))
    cat = validas.groupby("produto").agg(
        nome=("_nome", lambda s: s.mode().iloc[0]), tamanho=("tamanho_unitario", "median"),
        lojas=("cnpj", "nunique"), menor_preco=("valor_declarado", "min"),
        menor_preco_base=("preco_base", "min"), _todas=("_nome", lambda s: " | ".join(sorted(set(s))))).reset_index()
    if normalizar(marca):  # a marca pode estar em qualquer uma das descrições do produto
        cat = cat[_contem_marca(cat["_todas"], marca)]
    cat["rotulo"] = [
        f"{r.nome} · {tamanho_legivel(r.tamanho, unidade)} · {r.lojas} loja{'s' if r.lojas > 1 else ''} · "
        f"desde R$ {r.menor_preco:.2f}".replace(".", ",") for r in cat.itertuples()]
    return cat.sort_values(["lojas", "nome"], ascending=[False, True]).reset_index(drop=True)[colunas]
