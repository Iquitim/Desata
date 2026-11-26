"""Gera o desenho dos estados e a lista de municípios que o catálogo leva no programa (spec 049, RF-4958, RF-4965).

    uv run python scripts/gerar_mapa_brasil.py

Lê, uma vez, as fontes oficiais do IBGE e grava:

- ``src/prodata/web/js/brasil_mapa.js``: o contorno simplificado de cada estado (malha do IBGE, qualidade mínima),
  em caminhos SVG, para a navegação pelo mapa. Abrir o mapa não usa internet.
- ``src/prodata/catalog/municipios_ibge.json``: código, nome e UF de cada município, para a busca de lugares e a
  lista Demais municípios funcionarem sem internet.

Rodar de novo quando o IBGE criar ou mudar municípios. O programa nunca chama este script.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
MESH = "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
CITIES = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?view=nivelado"
WIDTH = 1000.0


def _rings(geometry: dict) -> list[list[list[float]]]:
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]
    return [ring for polygon in geometry["coordinates"] for ring in polygon]


def map_js(mesh: dict) -> str:
    rings = {f["properties"]["codarea"]: _rings(f["geometry"]) for f in mesh["features"]}
    points = [pt for rs in rings.values() for ring in rs for pt in ring]
    lon0, lon1 = min(p[0] for p in points), max(p[0] for p in points)
    lat0, lat1 = min(p[1] for p in points), max(p[1] for p in points)
    # Equirretangular com a correção da latitude média: o Brasil não fica achatado nem esticado.
    k = math.cos(math.radians((lat0 + lat1) / 2))
    scale = WIDTH / ((lon1 - lon0) * k)
    height = (lat1 - lat0) * scale

    def xy(pt: list[float]) -> str:
        return f"{(pt[0] - lon0) * k * scale:.1f},{(lat1 - pt[1]) * scale:.1f}"

    paths = {}
    for code, rs in sorted(rings.items()):
        paths[code] = " ".join("M" + " L".join(xy(pt) for pt in ring) + " Z" for ring in rs)
    body = ",\n".join(f"  '{code}': '{d}'" for code, d in paths.items())
    return (
        "// Gerado por scripts/gerar_mapa_brasil.py a partir da malha dos estados do IBGE (qualidade mínima).\n"
        "// Não edite à mão: rode o script de novo. Fonte: IBGE, API de malhas geográficas (v3).\n\n"
        f"export const VIEWBOX = '0 0 {WIDTH:.0f} {height:.0f}';\n\n"
        f"export const ESTADOS = {{\n{body},\n}};\n"
    )


def cities_json(rows: list[dict]) -> str:
    out = sorted([str(r["municipio-id"]), r["municipio-nome"], r["UF-sigla"]] for r in rows)
    return json.dumps(
        {"fonte": "IBGE, API de localidades (v1)", "municipios": out},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def main() -> int:
    with httpx.Client(timeout=120) as client:
        mesh = client.get(
            MESH, params={"formato": "application/vnd.geo+json", "qualidade": "minima", "intrarregiao": "UF"}
        ).json()
        cities = client.get(CITIES).json()
    if len(mesh["features"]) != 27 or len(cities) < 5500:
        print(f"Resposta inesperada do IBGE: {len(mesh['features'])} estados, {len(cities)} municípios.")
        return 1
    (ROOT / "src/prodata/web/js/brasil_mapa.js").write_text(map_js(mesh), encoding="utf-8")
    (ROOT / "src/prodata/catalog/municipios_ibge.json").write_text(cities_json(cities), encoding="utf-8")
    print(f"Gravados: 27 estados e {len(cities)} municípios.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
