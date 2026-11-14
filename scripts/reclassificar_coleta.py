"""Reclassifica coletas já publicadas com as regras atuais da cesta (sem consultar a API).

Baixa ofertas.parquet de cada coleta, refaz a classificação, gera de novo lojas e municípios e
grava em --saida/<tag>/, além do coletas.json atualizado em --saida/. O workflow
.github/workflows/reclassificar.yml envia os arquivos de volta às Releases.

    python scripts/reclassificar_coleta.py --indice coletas.json --tag todas --saida reclass/
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from economiza import coleta as col  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--indice", type=Path, required=True, help="coletas.json publicado")
    p.add_argument("--tag", default="todas", help="tag da coleta (ex.: coleta-2026-11-13) ou 'todas'")
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--pasta-local", type=Path, help="ler as coletas de uma pasta local (testes)")
    args = p.parse_args(argv)

    indice = json.loads(args.indice.read_text(encoding="utf-8"))
    alvo = [c for c in indice if not c.get("demo") and (args.tag == "todas" or c["tag"] == args.tag)]
    if not alvo:
        print(f"Nenhuma coleta encontrada para {args.tag!r}.", file=sys.stderr)
        return 1
    for coleta in alvo:
        ofertas = col.reclassificar(col.ler_tabela(coleta, "ofertas", args.pasta_local))
        tabelas = col.montar_tabelas(ofertas, coleta["data_coleta"])
        extra = {k: v for k, v in coleta.items() if k not in ("arquivos", "estado")}
        extra["reclassificada_em"] = datetime.now(col._FUSO).date().isoformat()
        antes = coleta["estado"]["lojas_com_cesta"]
        manifesto = col.salvar(tabelas, args.saida / coleta["tag"], extra, indice)
        indice = [manifesto if c["tag"] == coleta["tag"] else c for c in indice]
        print(f"{coleta['tag']}: lojas com a cesta completa {antes} -> {manifesto['estado']['lojas_com_cesta']}")
    (args.saida / "coletas.json").write_text(json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
