"""Coleta estadual da cesta básica em Parquet (usada pelo GitHub Actions a cada 10 dias).

Exemplos:
    python scripts/coleta_estadual.py --saida coleta/                 # os 102 municípios
    python scripts/coleta_estadual.py --municipios MACEIO PENEDO --saida teste/
    python scripts/coleta_estadual.py --saida coleta/ --indice-anterior coletas.json --exigir-token

Gera em ``--saida``: ofertas.parquet, lojas.parquet, municipios.parquet, manifesto.json
(linhas e bytes de cada arquivo), coletas.json (índice com o histórico) e resumo.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from economiza import obter_cliente  # noqa: E402
from economiza.coleta import INTERVALO_DIAS, PREFIXO_TAG, coletar, hoje, montar_tabelas, salvar  # noqa: E402
from economiza.municipios import NOMES_MUNICIPIOS, normalizar  # noqa: E402

LIMITE_FALHAS = 0.5  # mais da metade das consultas falhou -> não publica


def resumo_markdown(m: dict) -> str:
    e = m["estado"]
    linhas = [
        f"Coleta de **{m['data_coleta']}** — notas fiscais dos {m['dias']} dias anteriores, "
        f"{m['municipios_consultados']} municípios, {m['consultas']} consultas em {m['duracao_min']:.0f} min.",
        "",
        f"- Municípios com dados: {e['municipios_com_dados']} · com ao menos uma cesta completa: {e['municipios_com_cesta']}",
        f"- Estabelecimentos: {e['lojas']} · com a cesta completa: {e['lojas_com_cesta']}",
    ]
    if e["cesta_mediana"]:
        linhas.append(f"- Cesta (opção mais barata de cada loja): mediana R$ {e['cesta_mediana']:.2f}, "
                      f"de R$ {e['cesta_menor']:.2f} a R$ {e['cesta_maior']:.2f}")
    linhas += ["", "| Arquivo | Linhas | Tamanho |", "|---|---:|---:|"]
    for nome, info in m["arquivos"].items():
        linhas.append(f"| {nome}.parquet | {info['linhas']:,} | {info['bytes'] / 1e6:.2f} MB |")
    if m["falhas"]:
        linhas += ["", f"Consultas que falharam ({len(m['falhas'])}): " + ", ".join(m["falhas"][:30])]
    linhas += ["", "Metodologia: docs/CESTA_BASICA.md. Dados: API Economiza Alagoas (SEFAZ-AL)."]
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--municipios", nargs="+", help="padrão: os 102 municípios")
    p.add_argument("--dias", type=int, default=INTERVALO_DIAS)
    p.add_argument("--pausa", type=float, default=0.3, help="segundos entre consultas")
    p.add_argument("--paralelo", type=int, default=3, help="municípios consultados ao mesmo tempo")
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--data", default=None, help="data da coleta (padrão: hoje, horário de Maceió)")
    p.add_argument("--indice-anterior", type=Path, help="coletas.json já publicado, para manter o histórico")
    p.add_argument("--exigir-token", action="store_true", help="falha se não houver token (evita publicar dados fictícios)")
    args = p.parse_args(argv)

    cliente = obter_cliente()
    demo = getattr(cliente, "demo", False)
    if demo and args.exigir_token:
        print("ERRO: ECONOMIZA_AL_TOKEN não configurado.", file=sys.stderr)
        return 2
    municipios = [normalizar(m) for m in args.municipios] if args.municipios else NOMES_MUNICIPIOS
    data = args.data or hoje()

    inicio = time.time()
    ofertas, falhas, consultas = coletar(
        cliente, municipios, args.dias, args.pausa,
        progresso=lambda n, total, nome: print(f"[{n}/{total}] {nome}", flush=True),
        paralelo=args.paralelo)
    if consultas and len(falhas) / consultas > LIMITE_FALHAS:
        print(f"ERRO: {len(falhas)} de {consultas} consultas falharam; coleta não publicada.", file=sys.stderr)
        return 1

    indice = json.loads(args.indice_anterior.read_text(encoding="utf-8")) \
        if args.indice_anterior and args.indice_anterior.exists() else []
    extra = {"tag": PREFIXO_TAG + data, "data_coleta": data, "dias": args.dias, "demo": demo,
             "municipios_consultados": len(municipios), "consultas": consultas, "falhas": falhas,
             "duracao_min": (time.time() - inicio) / 60}
    manifesto = salvar(montar_tabelas(ofertas, data), args.saida, extra, indice)
    (args.saida / "resumo.md").write_text(resumo_markdown(manifesto), encoding="utf-8")
    print(resumo_markdown(manifesto))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
