"""PDFs sintéticos da spec 037 (dados inventados), gerados de HTML pelo Chrome e guardados em tests/fixtures/pdf/.

    uv run --with pypdfium2 --with pillow --with pypdf python specs/037-leitor-visual-pdf/spike/gerar_pdfs.py

Cada arquivo exercita uma situação do leitor: campos com rótulo, cabeçalho deslocado, dois totais, valor inválido,
tabela com célula de várias linhas que continua na página seguinte, página girada, conteúdo girado dentro do PDF, escaneado, protegido e quebrado.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "tests" / "fixtures" / "pdf"
BROWSERS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]

STYLE = """
@page { size: A4; margin: 18mm 16mm; }
body { font: 10.5pt Arial, sans-serif; color: #111; }
h1 { font-size: 16pt; margin: 0 0 4mm; }
.meta p { margin: 1.5mm 0; }
.extra { margin: 6mm 0; color: #444; }
table { width: 100%; border-collapse: collapse; margin-top: 6mm; }
th, td { border-bottom: 1px solid #bbb; padding: 2mm 1.5mm; text-align: left; vertical-align: top; }
th { background: #eee; }
td.num { text-align: right; white-space: nowrap; }
col.filial { width: 26%; } col.valor { width: 22%; } col.obs { width: 52%; }
.total td { font-weight: bold; border-top: 2px solid #333; }
.nota { margin-top: 8mm; font-size: 9pt; color: #555; }
"""

FILIAIS = [
    ("São Paulo", "52.000,00", "Meta atingida no trimestre"),
    ("Rio de Janeiro", "38.500,00", "Inclui o reajuste de contrato aplicado em setembro e o ajuste da nota de crédito"),
    ("Belo Horizonte", "34.930,00", "Sem observações"),
    ("Curitiba", "21.400,50", "Abertura da segunda loja"),
    ("Porto Alegre", "18.250,00", "Sazonalidade de inverno"),
    ("Salvador", "16.780,25", "Campanha regional com resultado acima do previsto em duas semanas seguidas"),
    ("Recife", "14.020,00", "Sem observações"),
    ("Fortaleza", "12.640,75", "Troca de gerente"),
]


def brl(cents: int) -> str:
    whole, frac = divmod(cents, 100)
    return f"R$ {whole:,}".replace(",", ".") + f",{frac:02d}"


def report(competencia: str, total: str | None = None, *, extra: str = "", rows: int = 8, repeat_rows: int = 1,
           nota: str = "") -> str:
    """Relatório sintético. 'Total geral' é sempre a soma das linhas; 'Total líquido' é o informado (ou a soma)."""
    items = (FILIAIS * repeat_rows)[: rows * repeat_rows]
    body = "".join(f"<tr><td>{f}</td><td class='num'>R$ {v}</td><td>{o}</td></tr>" for f, v, o in items)
    soma = brl(sum(int(v.replace(".", "").replace(",", "")) for _, v, _ in items))
    comp = f"<p>Competência: {competencia}</p>" if competencia else ""
    return f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><style>{STYLE}</style><body>
<h1>RELATÓRIO MENSAL DE VENDAS</h1>
{extra}
<div class="meta">{comp}<p>Emitido por: Controladoria</p><p>Total líquido: {total or soma}</p></div>
<table><colgroup><col class="filial"><col class="valor"><col class="obs"></colgroup>
<thead><tr><th>Filial</th><th>Valor</th><th>Observação</th></tr></thead>
<tbody>{body}<tr class="total"><td>Total geral</td><td class="num">{soma}</td><td></td></tr></tbody></table>
{nota}
</body></html>"""


DOCS = {
    "relatorio_outubro.pdf": report("10/2026", repeat_rows=4),
    "relatorio_novembro.pdf": report(
        "11/2026", rows=7,
        extra="<p class='extra'>Este relatório consolida as vendas das filiais próprias. Os valores estão em reais, "
              "já descontadas as devoluções do período e as notas de crédito emitidas até o último dia útil.</p>"
              "<p class='extra'>Dúvidas: controladoria@exemplo.com.br</p>",
    ),
    "relatorio_dois_totais.pdf": report(
        "12/2026", "R$ 150.000,00",
        nota="<div class='nota'><p>Total líquido: R$ 149.500,00</p><p>(valor revisado após o fechamento)</p></div>",
    ),
    "relatorio_invalido.pdf": report("", "a definir"),
}


def chrome() -> str:
    found = next((b for b in BROWSERS if b.is_file()), None) or shutil.which("chrome") or shutil.which("msedge")
    if not found:
        sys.exit("Chrome ou Edge não encontrado.")
    return str(found)


def print_pdf(html: str, target: Path, browser: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "doc.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run(
            [browser, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={Path(tmp) / 'p'}",
             "--no-pdf-header-footer", f"--print-to-pdf={target}", page.as_uri()],
            check=True, capture_output=True,
        )  # fmt: skip


def main() -> None:
    import pypdfium2 as pdfium
    from pypdf import PdfReader, PdfWriter

    OUT.mkdir(parents=True, exist_ok=True)
    browser = chrome()
    for name, html in DOCS.items():
        print_pdf(html, OUT / name, browser)

    # Página girada: o mesmo relatório de novembro, com a página 1 girada 90 graus.
    doc = pdfium.PdfDocument(OUT / "relatorio_novembro.pdf")
    doc[0].set_rotation(90)
    doc.save(OUT / "relatorio_girado.pdf")

    # Rotação interna: o conteúdo corre na vertical dentro do PDF e a página tem /Rotate 90, então na tela o texto
    # aparece normal. É como muitos sistemas geram relatórios "em paisagem".
    from pypdf import Transformation

    inner = PdfWriter(clone_from=OUT / "relatorio_novembro.pdf")
    for page in inner.pages:
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        page.add_transformation(Transformation().rotate(90).translate(tx=h, ty=0))
        page.mediabox.lower_left, page.mediabox.upper_right = (0, 0), (h, w)
        page.cropbox.lower_left, page.cropbox.upper_right = (0, 0), (h, w)
        page.rotate(90)
    with (OUT / "relatorio_rotacao_interna.pdf").open("wb") as fh:
        inner.write(fh)

    # Escaneado: só imagem, sem camada de texto.
    image = pdfium.PdfDocument(OUT / "relatorio_outubro.pdf")[0].render(scale=1.5).to_pil().convert("RGB")
    image.save(OUT / "relatorio_escaneado.pdf", "PDF", resolution=108)

    # Protegido por senha.
    reader = PdfReader(OUT / "relatorio_novembro.pdf")
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt("segredo")
    buf = io.BytesIO()
    writer.write(buf)
    (OUT / "relatorio_protegido.pdf").write_bytes(buf.getvalue())

    # Quebrado: o começo de um PDF de verdade, cortado no meio.
    data = (OUT / "relatorio_outubro.pdf").read_bytes()
    (OUT / "relatorio_quebrado.pdf").write_bytes(data[: len(data) // 3])

    for f in sorted(OUT.glob("*.pdf")):
        print(f"{f.name:28} {f.stat().st_size:>8} bytes")


if __name__ == "__main__":
    main()
