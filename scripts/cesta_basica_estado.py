"""Cesta básica em vários municípios de Alagoas (ou no estado inteiro).

Gera, na pasta de saída:
- ``ofertas/<IBGE>.csv.gz``  ofertas classificadas de cada município (cache: rodar de novo
  pula os municípios já baixados, então dá para retomar se a API cair no meio);
- ``lojas.csv`` e ``lojas.geojson``  uma linha por estabelecimento, com a cesta (abre no QGIS);
- ``municipios.csv``  indicadores por município (lojas, % com cesta completa, menor, mediana,
  média e maior cesta, horas de trabalho). Junte com a malha do IBGE pelo ``codigo_ibge``
  para fazer um mapa coroplético.

Uso:
    python scripts/cesta_basica_estado.py --municipios MACEIO ARAPIRACA
    python scripts/cesta_basica_estado.py --todos --dias 7 --saida resultados/

Sem ``ECONOMIZA_AL_TOKEN`` o script roda com os dados FICTÍCIOS do modo demonstração.
São 19 consultas por município (1.938 para o estado): use ``--pausa`` para não
sobrecarregar a API da SEFAZ.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from economiza import coleta, obter_cliente  # noqa: E402
from economiza import cesta_basica as cb  # noqa: E402
from economiza.mapa import para_geojson  # noqa: E402
from economiza.municipios import MUNICIPIOS_AL, NOMES_MUNICIPIOS, codigo_ibge, normalizar  # noqa: E402


def baixar_municipio(cliente, ibge: int, dias: int, pausa: float) -> pd.DataFrame:
    ofertas, falhas = coleta.baixar_municipio(cliente, ibge, dias, pausa)
    for falha in falhas:
        print(f"    ! {falha}", file=sys.stderr)
    return cb.classificar_ofertas(ofertas) if not ofertas.empty else ofertas


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    alvo = p.add_mutually_exclusive_group(required=True)
    alvo.add_argument("--municipios", nargs="+", help="nomes dos municípios (ex.: MACEIO ARAPIRACA)")
    alvo.add_argument("--todos", action="store_true", help="os 102 municípios de Alagoas")
    p.add_argument("--dias", type=int, default=7, help="período das notas fiscais (1 a 10)")
    p.add_argument("--saida", type=Path, default=Path("resultados_cesta"))
    p.add_argument("--pausa", type=float, default=0.5, help="segundos entre consultas à API")
    args = p.parse_args(argv)

    nomes = NOMES_MUNICIPIOS if args.todos else [normalizar(n) for n in args.municipios]
    cache = args.saida / "ofertas"
    cache.mkdir(parents=True, exist_ok=True)
    cliente = obter_cliente()
    if getattr(cliente, "demo", False):
        print("AVISO: sem ECONOMIZA_AL_TOKEN -> dados FICTÍCIOS (modo demonstração).", file=sys.stderr)

    todas = []
    for n, nome in enumerate(nomes, start=1):
        ibge = codigo_ibge(nome)
        arquivo = cache / f"{ibge}.csv.gz"
        if arquivo.exists():
            print(f"[{n}/{len(nomes)}] {nome}: em cache")
            ofertas = pd.read_csv(arquivo, dtype={"cnpj": "string"}, parse_dates=["data_venda"])
        else:
            print(f"[{n}/{len(nomes)}] {nome}: consultando…")
            ofertas = baixar_municipio(cliente, ibge, args.dias, args.pausa)
            ofertas.to_csv(arquivo, index=False)
        if ofertas.empty:
            continue
        cestas = cb.cestas_por_estabelecimento(ofertas)
        cestas["municipio"] = nome
        cestas["codigo_ibge"] = ibge
        todas.append(cestas)

    if not todas:
        print("Nenhum dado obtido.", file=sys.stderr)
        return 1
    lojas = pd.concat(todas, ignore_index=True)
    lojas.to_csv(args.saida / "lojas.csv", index=False)
    (args.saida / "lojas.geojson").write_text(para_geojson(lojas, list(lojas.columns)), encoding="utf-8")

    indicadores = cb.indicadores(lojas, por="municipio")
    indicadores.insert(1, "codigo_ibge", indicadores["municipio"].map(MUNICIPIOS_AL))
    indicadores = indicadores.sort_values("mediana").round(2)
    indicadores.to_csv(args.saida / "municipios.csv", index=False)
    print(indicadores[["municipio", "estabelecimentos", "com_cesta_completa", "menor_cesta", "mediana", "maior_cesta"]]
          .to_string(index=False))
    print(f"\nArquivos em {args.saida.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
