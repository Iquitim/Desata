"""Leitura de PDF com pypdfium2 (spec 037). Roda só dentro do processo isolado (``worker.py``).

Toda caixa sai **normalizada**: de 0 a 1, origem no canto superior esquerdo da página como ela aparece na tela, com a
rotação da página já aplicada. Assim a tela posiciona as palavras em porcentagem sobre a imagem, e o alinhamento não
depende de zoom, escala da tela nem resolução da imagem.

Nenhuma mensagem de erro leva texto do documento: só o código da falha.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

MAX_BYTES = 200 * 2**20  # 200 MB
MAX_PAGES = 2000
MAX_PIXELS = 24_000_000  # imagem da página: no máximo ~24 megapixels
MAX_SCALE = 4.0


class PdfReadError(Exception):
    """Falha de leitura com código estável (``protegido``, ``malformado``, ``sem_texto``, ``grande_demais``...)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail  # nunca com conteúdo do documento


@dataclass(frozen=True)
class Word:
    text: str
    page: int  # começa em 0
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 normalizados, origem em cima à esquerda

    def as_dict(self) -> dict[str, Any]:
        return {"t": self.text, "p": self.page, "b": [round(v, 5) for v in self.box]}


def _open(path: Path, password: str | None = None) -> Any:
    import pypdfium2 as pdfium

    size = path.stat().st_size
    if size > MAX_BYTES:
        raise PdfReadError("grande_demais", f"{size // 2**20} MB; o limite é {MAX_BYTES // 2**20} MB")
    try:
        doc = pdfium.PdfDocument(path, password=password)
    except pdfium.PdfiumError as exc:
        text = str(exc).lower()
        if "password" in text or "senha" in text:
            raise PdfReadError("protegido") from None
        raise PdfReadError("malformado") from None
    if len(doc) > MAX_PAGES:
        raise PdfReadError("grande_demais", f"{len(doc)} páginas; o limite é {MAX_PAGES}")
    return doc


def _rotate(u0: float, v0: float, u1: float, v1: float, rotation: int) -> tuple[float, float, float, float]:
    """Caixa normalizada na página sem rotação (v de cima para baixo) → como a página aparece girada (horário)."""
    corners = [(u0, v0), (u1, v1)]
    if rotation == 90:
        pts = [(1 - v, u) for u, v in corners]
    elif rotation == 180:
        pts = [(1 - u, 1 - v) for u, v in corners]
    elif rotation == 270:
        pts = [(v, 1 - u) for u, v in corners]
    else:
        pts = corners
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


_FRAME = {  # direção do texto no PDF (graus, anti-horário, y para cima) → giro que deixa o texto correndo para +x
    0: lambda x, y: (x, y),
    90: lambda x, y: (y, -x),
    180: lambda x, y: (-x, -y),
    270: lambda x, y: (-y, x),
}
_UNFRAME = {
    0: lambda x, y: (x, y),
    90: lambda x, y: (-y, x),
    180: lambda x, y: (-x, -y),
    270: lambda x, y: (y, -x),
}
Quad = tuple[float, float, float, float]


def _map(box: Quad, fn: Any) -> Quad:
    (ax, ay), (bx, by) = fn(box[0], box[1]), fn(box[2], box[3])
    return min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)


def _direction(chars: list[tuple[str, Quad] | None]) -> int:
    """Direção dominante do texto, pela sequência dos caracteres de uma mesma palavra (0, 90, 180 ou 270)."""
    votes = {0: 0, 90: 0, 180: 0, 270: 0}
    for a, b in pairwise(chars):
        if a is None or b is None:
            continue
        (ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1) = a[1], b[1]
        dx, dy = (bx0 + bx1 - ax0 - ax1) / 2, (by0 + by1 - ay0 - ay1) / 2
        size = max(ax1 - ax0, ay1 - ay0, bx1 - bx0, by1 - by0, 1.0)
        if not 0 < abs(dx) + abs(dy) < 3 * size:
            continue  # quebra de linha ou de coluna: não diz a direção
        if abs(dx) >= abs(dy):
            votes[0 if dx > 0 else 180] += 1
        else:
            votes[90 if dy > 0 else 270] += 1
    return max(votes, key=lambda k: (votes[k], k == 0))


def _page_words(page: Any, index: int) -> tuple[list[Word], int]:
    """Caracteres viram palavras: quebra em espaço, em mudança de linha e em distância grande entre letras.

    O agrupamento acontece no referencial em que o texto corre da esquerda para a direita, qualquer que seja a
    direção dele dentro do PDF (relatório em paisagem feito como página em pé girada, por exemplo). Devolve as
    palavras e o ângulo em que o texto aparece na tela (sentido horário), que o motor usa para ler na direção certa.
    """
    left, bottom, right, top = page.get_mediabox()
    width, height = right - left, top - bottom
    rotation = page.get_rotation() % 360
    # O PDFium reordena os caracteres pela rotação da página, misturando linhas quando ela está girada. Zerada só na
    # memória (o arquivo não é gravado), a ordem segue o conteúdo; a rotação volta na conversão para a tela.
    page.set_rotation(0)
    tp = page.get_textpage()
    chars: list[tuple[str, Quad] | None] = []
    for i in range(tp.count_chars()):
        ch = tp.get_text_range(i, 1)
        if not ch or ch.isspace() or ch in "\r\n\x02\ufffe":
            chars.append(None)
        else:
            chars.append((ch, tuple(tp.get_charbox(i, loose=True))))
    direction = _direction(chars)
    frame, unframe = _FRAME[direction], _UNFRAME[direction]
    words: list[Word] = []
    text, box = "", None

    def flush() -> None:
        nonlocal text, box
        if text and box:
            x0, y0, x1, y1 = _map(box, unframe)
            u0, u1 = (x0 - left) / width, (x1 - left) / width
            v0, v1 = (top - y1) / height, (top - y0) / height
            words.append(Word(text, index, _rotate(u0, v0, u1, v1, rotation)))
        text, box = "", None

    for item in chars:
        if item is None:
            flush()
            continue
        ch, raw = item
        x0, y0, x1, y1 = _map(raw, frame)
        if box is not None:
            line_height = max(box[3] - box[1], 1.0)
            same_line = abs((y0 + y1) / 2 - (box[1] + box[3]) / 2) < line_height * 0.5
            near = x0 - box[2] < line_height * 0.4
            if not (same_line and near):
                flush()
        text += ch
        box = (
            (x0, y0, x1, y1)
            if box is None
            else (min(box[0], x0), min(box[1], y0), max(box[2], x1), max(box[3], y1))
        )
    flush()
    page.set_rotation(rotation)
    return words, (rotation - direction) % 360


def inspect(path: str, password: str | None = None) -> dict[str, Any]:
    """Páginas (tamanho e rotação), palavras de todas as páginas e se há camada de texto."""
    doc = _open(Path(path), password)
    pages, words = [], []
    for i in range(len(doc)):
        page = doc[i]
        w, h = page.get_size()  # já como a página aparece, com a rotação
        rotation = page.get_rotation() % 360
        page_words, reading = _page_words(page, i)
        # r: rotação da página; t: ângulo (horário) em que o texto aparece na tela, 0 = normal
        pages.append({"w": round(w, 2), "h": round(h, 2), "r": rotation, "t": reading})
        words += [wd.as_dict() for wd in page_words]
    if not words:
        raise PdfReadError("sem_texto", f"{len(pages)} página(s) sem texto")
    return {"pages": pages, "words": words}


def render(path: str, page_index: int, scale: float, password: str | None = None) -> bytes:
    """Imagem PNG da página, com a rotação da página, dentro do limite de pixels."""
    doc = _open(Path(path), password)
    if not 0 <= page_index < len(doc):
        raise PdfReadError("pagina_inexistente")
    page = doc[page_index]
    w, h = page.get_size()
    scale = max(0.1, min(scale, MAX_SCALE))
    if w * h * scale * scale > MAX_PIXELS:
        scale = (MAX_PIXELS / (w * h)) ** 0.5
    image = page.render(scale=scale, may_draw_forms=False).to_pil()
    buf = io.BytesIO()
    image.save(buf, "PNG", optimize=False)
    return buf.getvalue()
