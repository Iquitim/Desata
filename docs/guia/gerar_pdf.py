"""Gera docs/guia/<nome curto>-Guia-do-Produto.pdf a partir de guia.html usando o Chrome/Edge headless.

    uv run python docs/guia/gerar_pdf.py [--marca <id>] [--imagens <pasta>]

--imagens: prints de outra pasta (com img/ dentro), como os de uma marca que ainda não é a padrão.

As marcações do guia ({{produto}}, cores, logo) são trocadas pela marca antes de imprimir (spec 036).

As capturas em img/ vêm do app rodando com o fluxo de demonstração.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from marca_guia import choose_brand, pdf_name, render  # noqa: E402

SOURCE = HERE / "guia.html"
RENDERED = HERE / "_guia_marca.html"  # ao lado do guia, para os caminhos relativos valerem
BROWSERS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


def check_prints(base: Path) -> None:
    """Spec 046: o guia só sai com prints da versão atual e da marca certa, feitos todos na mesma geração."""
    found = re.search(r'__version__ = "([^"]+)"', (HERE.parents[1] / "src/prodata/__init__.py").read_text(encoding="utf-8"))
    version = found.group(1) if found else "?"
    brand = os.environ.get("PRODATA_MARCA", "desata")
    manifest = base / "prints.json"
    info = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    if info.get("versao") != version or info.get("marca") != brand:
        sys.exit(
            f"Os prints em {base} são da versão {info.get('versao', '?')}, marca {info.get('marca', '?')}; o guia é da "
            f"{version}, marca {brand}. Rode a geração completa (docs/guia/imagens/gerar_imagens.py, sem IMAGENS_SO)."
        )


def main() -> None:
    choose_brand()
    images = None
    if "--imagens" in sys.argv:
        images = Path(sys.argv[sys.argv.index("--imagens") + 1]).resolve() / "img"
    check_prints(images.parent if images is not None else HERE.parents[1] / "src/prodata/web/manual")
    output = HERE / pdf_name()
    html = render(SOURCE.read_text(encoding="utf-8"))
    if images is not None:
        html = html.replace("../../src/prodata/web/manual/img/", images.as_uri() + "/")
    RENDERED.write_text(html, encoding="utf-8")
    browser = (
        next((b for b in BROWSERS if b.is_file()), None) or shutil.which("chrome") or shutil.which("msedge")
    )
    if not browser:
        sys.exit("Chrome ou Edge não encontrado.")
    with tempfile.TemporaryDirectory(prefix="prodata-guia-") as tmp:
        # O Chrome grava num diretório temporário e o arquivo é movido depois: falha de
        # escrita do navegador vira erro explícito em vez de deixar um PDF antigo no lugar.
        target = Path(tmp) / output.name
        subprocess.run(
            [
                str(browser), "--headless=new", "--disable-gpu", "--no-first-run",
                f"--user-data-dir={Path(tmp) / 'profile'}", "--no-pdf-header-footer", "--virtual-time-budget=5000",
                f"--print-to-pdf={target}", RENDERED.as_uri(),
            ],
            check=True, capture_output=True,
        )  # fmt: skip
        if not target.is_file():
            sys.exit("O navegador não gerou o PDF.")
        shutil.move(target, output)
    RENDERED.unlink(missing_ok=True)
    print(f"PDF gerado: {output} ({output.stat().st_size / 2**20:.1f} MB)")


if __name__ == "__main__":
    main()
