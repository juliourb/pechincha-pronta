import pandas as pd
import pytest
import requests

from economiza.api import (REGISTROS_POR_PAGINA, EconomizaAPIError, EconomizaClient,
                           filtrar_bairro, normalizar_resultado)


def registro(cnpj="1", bairro="Ponta Verde", preco=6.0, lat=-9.6, lon=-35.7, fantasia="Posto X"):
    return {
        "produto": {"descricao": "GASOLINA", "ncm": "27101259", "gtin": None,
                    "venda": {"dataVenda": "2026-01-10T10:00:00", "valorDeclarado": preco, "valorVenda": preco}},
        "estabelecimento": {"cnpj": cnpj, "razaoSocial": "RAZAO", "nomeFantasia": fantasia,
                            "endereco": {"bairro": bairro, "latitude": lat, "longitude": lon}},
    }


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body, self.text = status, body, str(body)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class SessaoFalsa(requests.Session):
    def __init__(self, respostas):
        super().__init__()
        self.respostas, self.payloads = list(respostas), []

    def post(self, url, json=None, timeout=None, **kw):
        assert timeout, "toda requisição deve ter timeout"
        self.payloads.append(json)
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def cliente(respostas):
    s = SessaoFalsa(respostas)
    return EconomizaClient("token-teste", session=s), s


def test_token_obrigatorio():
    with pytest.raises(ValueError):
        EconomizaClient("")


def test_header_e_payload_combustivel():
    c, s = cliente([Resp(body={"totalPaginas": 1, "conteudo": [registro()]})])
    df = c.pesquisar_combustivel(1, 2704302, dias=30)
    assert s.headers["AppToken"] == "token-teste"
    p = s.payloads[0]
    assert p["produto"] == {"tipoCombustivel": 1}
    assert p["estabelecimento"]["municipio"]["codigoIBGE"] == 2704302
    assert p["dias"] == 10  # limitado ao máximo da API
    assert df.loc[0, "valor_declarado"] == 6.0
    assert df.loc[0, "estabelecimento"] == "Posto X"


def test_paginacao_por_total_paginas():
    c, s = cliente([Resp(body={"totalPaginas": 2, "conteudo": [registro("1")]}),
                    Resp(body={"totalPaginas": 2, "conteudo": [registro("2")]})])
    df = c.pesquisar_produto(2704302, descricao="picanha", ncm="02013000")
    assert list(df["cnpj"]) == ["1", "2"]
    assert [p["pagina"] for p in s.payloads] == [1, 2]
    assert s.payloads[0]["produto"] == {"descricao": "PICANHA", "ncm": "02013000"}


def test_paginacao_sem_total_paginas_para_em_pagina_incompleta():
    cheia = [registro(str(i)) for i in range(REGISTROS_POR_PAGINA)]
    c, s = cliente([Resp(body={"conteudo": cheia}), Resp(body={"conteudo": [registro("x")]})])
    df = c.pesquisar_produto(2704302, ncm="02013000")
    assert len(df) == REGISTROS_POR_PAGINA + 1 and len(s.payloads) == 2


@pytest.mark.parametrize("resposta", [Resp(status=401, body="não autorizado"),
                                      Resp(body=ValueError("html")),
                                      requests.Timeout("lento")])
def test_erros_viram_economiza_api_error(resposta):
    c, _ = cliente([resposta])
    with pytest.raises(EconomizaAPIError):
        c.pesquisar_combustivel(1, 2704302)


def test_resposta_vazia_tem_colunas_padrao():
    c, _ = cliente([Resp(body={"totalPaginas": 0, "conteudo": []})])
    df = c.pesquisar_combustivel(1, 2704302)
    assert df.empty and "valor_declarado" in df.columns


def test_coordenada_zero_vira_nula_e_fantasia_vazia_usa_razao():
    df = normalizar_resultado([registro(lat=0, lon=0, fantasia="")])
    assert pd.isna(df.loc[0, "latitude"]) and df.loc[0, "estabelecimento"] == "RAZAO"


def test_filtro_bairro_sem_acento_e_parcial():
    df = normalizar_resultado([registro("1", "Jatiúca"), registro("2", "Centro"), registro("3", None)])
    assert list(filtrar_bairro(df, "jatiuca")["cnpj"]) == ["1"]
    assert list(filtrar_bairro(df, "CENT")["cnpj"]) == ["2"]
    assert len(filtrar_bairro(df, "")) == 3
