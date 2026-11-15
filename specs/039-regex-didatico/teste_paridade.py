"""O gerador da tela (regex_builder.js) monta o mesmo padrão que o Python (regex_pieces.py). Com o app aberto na porta 8791:

    uv run --with playwright python specs/039-regex-didatico/teste_paridade.py
"""
import json
import os
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "src"))
from playwright.sync_api import sync_playwright  # noqa: E402

from prodata.nodes.regex_pieces import PIECES, RegexPiece, catalog, names_of, pattern_of  # noqa: E402

cases = []
for kind in PIECES:
    for count in (None, 1, 3):
        for take in (False, True):
            cases.append([{"kind": kind, "count": count, "take": take, "name": "c" if take else "", "text": "R$ (x).?" if kind == "literal" else ""}])
cases.append([{"kind": "literal", "text": "NF "}, {"kind": "digits", "count": 2, "take": True, "name": "mes"}, {"kind": "literal", "text": "/"}, {"kind": "digits", "count": 4, "take": True, "name": "ano"}])
cases.append([{"kind": "start"}, {"kind": "word"}, {"kind": "space", "count": 1}, {"kind": "decimal", "take": True}, {"kind": "end"}])
expected = [[pattern_of([RegexPiece(**p) for p in c]), names_of([RegexPiece(**p) for p in c])] for c in cases]
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page()
    page.goto("http://127.0.0.1:8791/")
    got = page.evaluate(
        """async ([cases, cat]) => { const R = await import('/static/js/regex_builder.js');
        return cases.map((c) => [R.patternOf(c, cat), R.namesOf(c)]); }""",
        [cases, catalog()],
    )
    b.close()
bad = [(c, e, g) for c, e, g in zip(cases, expected, got, strict=True) if e != g]
print(f"{len(cases)} casos, {len(bad)} diferentes")
for c, e, g in bad[:5]:
    print(json.dumps(c, ensure_ascii=False), "python:", e, "tela:", g)
os._exit(1 if bad else 0)
