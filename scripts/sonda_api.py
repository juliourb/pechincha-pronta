"""Sondagem da API: compara estratégias de consulta (termo + NCM x só o termo).

Ferramenta de diagnóstico, rodada pelo workflow .github/workflows/sonda.yml. Para cada
município e item da cesta básica, mostra quantas ofertas e lojas cada consulta devolve e
quais descrições novas seriam aceitas sem o filtro de NCM (para revisar falsos positivos).

    python scripts/sonda_api.py --municipios MACEIO BATALHA
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from economiza import EconomizaAPIError, obter_cliente  # noqa: E402
from economiza import cesta_basica as cb  # noqa: E402
from economiza.municipios import codigo_ibge, normalizar  # noqa: E402

TERMOS_LIVRES = {
    "Carne": ["PATINHO", "COXAO", "CHA DENTRO", "CHA FORA"],
    "Leite": ["LEITE"], "Feijão": ["FEIJAO"], "Arroz": ["ARROZ"],
    "Farinha": ["FARINHA MANDIOCA", "FARINHA"], "Tomate": ["TOMATE"],
    "Pão francês": ["PAO FRANCES", "PAO"], "Café em pó": ["CAFE"], "Banana": ["BANANA"],
    "Açúcar": ["ACUCAR"], "Óleo": ["OLEO SOJA", "OLEO"], "Manteiga": ["MANTEIGA"],
}


def consultar(cliente, ibge, termo, ncm, dias):
    inicio = time.time()
    try:
        df = cliente.pesquisar_produto(ibge, descricao=termo, ncm=ncm, dias=dias)
        erro = ""
    except EconomizaAPIError as e:
        df, erro = pd.DataFrame(), str(e)[:120]
    return df, time.time() - inicio, erro


def lojas_ok(df, item):
    if df.empty:
        return 0, pd.DataFrame()
    cl = cb.classificar_ofertas(cb.remover_duplicadas(df.assign(item=item)))
    ok = cl[cl["motivo"] == "ok"]
    return ok["cnpj"].nunique(), ok


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--municipios", nargs="+", required=True)
    p.add_argument("--dias", type=int, default=10)
    p.add_argument("--itens", nargs="*")
    args = p.parse_args(argv)
    cliente = obter_cliente()
    print("modo demonstração:", getattr(cliente, "demo", False))
    for nome in args.municipios:
        ibge = codigo_ibge(nome)
        print(f"\n================ {normalizar(nome)} ({ibge})")
        for item in cb.ITENS_REGIAO_2:
            if args.itens and item.nome not in args.itens:
                continue
            com_ncm = []
            for termo in item.termos:
                for ncm in item.ncms:
                    df, _, _ = consultar(cliente, ibge, termo, ncm, args.dias)
                    com_ncm.append(df)
            base = pd.concat(com_ncm, ignore_index=True) if com_ncm else pd.DataFrame()
            n_base, ok_base = lojas_ok(base, item.nome)
            print(f"\n## {item.nome}: termo+NCM -> {len(base)} linhas, {n_base} lojas ok")
            for termo in TERMOS_LIVRES[item.nome]:
                df, seg, erro = consultar(cliente, ibge, termo, None, args.dias)
                n, ok = lojas_ok(df, item.nome)
                print(f"   só '{termo}': {len(df)} linhas em {seg:.0f}s, {n} lojas ok {erro}")
                if ok.empty:
                    continue
                novas = ok[~ok["descricao"].isin(set(ok_base.get("descricao", [])))]
                if not novas.empty:
                    top = (novas.assign(ncm=novas["ncm"].astype(str))
                           .groupby(["descricao", "ncm", "unidade_medida"]).size()
                           .sort_values(ascending=False).head(14))
                    print(f"      novas aceitas: {novas['descricao'].nunique()} descrições, "
                          f"{novas['cnpj'].nunique()} lojas. Exemplos:")
                    for (d, ncm, um), q in top.items():
                        print(f"        {q:>3}x [{ncm}] [{um}] {d[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
