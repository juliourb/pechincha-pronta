"""Baixa a malha municipal de Alagoas e grava em data/malha_municipios_al.geojson.

O app usa este arquivo local (rápido e sem depender do IBGE estar acessível). Rodado pelo
workflow .github/workflows/malha.yml; localmente:  python scripts/baixar_malha.py
Usa só a biblioteca padrão. Coordenadas arredondadas a 5 casas (~1 m) para reduzir o arquivo.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from economiza.coleta import ARQUIVO_MALHA, FONTES_MALHA, codigo_da_feicao  # noqa: E402
from economiza.municipios import MUNICIPIOS_AL, nome_oficial  # noqa: E402


def _arredondar(coords, casas: int = 5):
    if isinstance(coords[0], (int, float)):
        return [round(c, casas) for c in coords]
    return [_arredondar(c, casas) for c in coords]


def preparar(malha: dict) -> dict:
    """Mantém só código e nome oficial em cada polígono e confere os 102 municípios."""
    nomes = {cod: nome_oficial(n) for n, cod in MUNICIPIOS_AL.items()}
    feicoes = []
    for f in malha["features"]:
        cod = codigo_da_feicao(f)
        if cod in nomes:
            geom = {"type": f["geometry"]["type"], "coordinates": _arredondar(f["geometry"]["coordinates"])}
            feicoes.append({"type": "Feature", "properties": {"codigo_ibge": cod, "nome": nomes[cod]},
                            "geometry": geom})
    faltando = set(nomes) - {f["properties"]["codigo_ibge"] for f in feicoes}
    if faltando:
        raise ValueError(f"Malha incompleta: faltam {len(faltando)} municípios")
    return {"type": "FeatureCollection", "features": sorted(feicoes, key=lambda f: f["properties"]["codigo_ibge"])}


def main() -> int:
    for url in FONTES_MALHA:
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                malha = preparar(json.load(resp))
        except Exception as erro:  # tenta a próxima fonte
            print(f"Falhou: {url}\n  {erro}", file=sys.stderr)
            continue
        ARQUIVO_MALHA.parent.mkdir(exist_ok=True)
        ARQUIVO_MALHA.write_text(json.dumps(malha, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"OK: {len(malha['features'])} municípios de {url} -> {ARQUIVO_MALHA} "
              f"({ARQUIVO_MALHA.stat().st_size / 1e6:.2f} MB)")
        return 0
    print("Nenhuma fonte da malha respondeu.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
