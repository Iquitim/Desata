"""Palavras → linhas, e busca de rótulos nas linhas (spec 037).

As palavras chegam do leitor como ``{"t": texto, "p": página, "b": [x0, y0, x1, y1]}``, com caixa normalizada. As
distâncias horizontais são comparadas com a altura da linha já na mesma escala (usa a proporção da página), para que
"espaço grande" signifique o mesmo em retrato e paisagem.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from prodata.documents.types import normalize

Word = dict[str, Any]
Box = tuple[float, float, float, float]


def union(boxes: Iterable[Sequence[float]]) -> Box:
    items = list(boxes)
    return (
        min(b[0] for b in items),
        min(b[1] for b in items),
        max(b[2] for b in items),
        max(b[3] for b in items),
    )


def norm_word(text: str) -> str:
    """Palavra comparável: sem acento, minúscula, sem pontuação nas pontas ('líquido:' → 'liquido')."""
    return normalize(text).strip(":;,.()[]\"'–-")


def norm_tokens(text: str) -> list[str]:
    return [t for t in (norm_word(w) for w in text.split()) if t]


@dataclass
class Line:
    page: int
    aspect: float  # altura / largura da página
    words: list[Word] = field(default_factory=list)

    @property
    def top(self) -> float:
        return min(w["b"][1] for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w["b"][3] for w in self.words)

    @property
    def middle(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def height(self) -> float:
        return max(self.bottom - self.top, 1e-4)

    @property
    def box(self) -> Box:
        return union(w["b"] for w in self.words)

    @property
    def text(self) -> str:
        return " ".join(w["t"] for w in self.words)

    def tokens(self) -> list[str]:
        return [norm_word(w["t"]) for w in self.words]

    def gap(self, left: Word, right: Word) -> float:
        """Distância horizontal entre duas palavras, em alturas de linha."""
        return (right["b"][0] - left["b"][2]) / (self.height / self.aspect)


def to_reading(box: Sequence[float], angle: int) -> Box:
    """Caixa na tela → espaço de leitura (texto correndo da esquerda para a direita, linhas de cima para baixo)."""
    x0, y0, x1, y1 = box
    if angle == 90:  # texto descendo na tela: a primeira linha fica à direita
        return y0, 1 - x1, y1, 1 - x0
    if angle == 180:
        return 1 - x1, 1 - y1, 1 - x0, 1 - y0
    if angle == 270:  # texto subindo
        return 1 - y1, x0, 1 - y0, x1
    return x0, y0, x1, y1


def to_screen(box: Sequence[float], angle: int) -> Box:
    """O inverso de :func:`to_reading`."""
    x0, y0, x1, y1 = box
    if angle == 90:
        return 1 - y1, x0, 1 - y0, x1
    if angle == 180:
        return 1 - x1, 1 - y1, 1 - x0, 1 - y0
    if angle == 270:
        return y0, 1 - x1, y1, 1 - x0
    return x0, y0, x1, y1


def group_lines(words: Sequence[Word], pages: Sequence[dict[str, Any]]) -> list[Line]:
    """Agrupa por página e altura: palavras cujo meio está a menos de meia altura do meio da linha ficam juntas.

    Tudo acontece no espaço de leitura da página (``t`` do leitor): numa página girada, "à direita" e "abaixo" seguem
    o texto, não a tela. Cada palavra das linhas leva ``b`` (leitura) e ``d`` (tela, para a origem).
    """
    lines: list[Line] = []
    by_page: dict[int, list[Word]] = {}
    for w in words:
        by_page.setdefault(w["p"], []).append(w)
    for page in sorted(by_page):
        info = pages[page] if page < len(pages) else {"w": 1, "h": 1}
        angle = int(info.get("t", 0))
        aspect = info["h"] / info["w"] if info["w"] else 1.0
        if angle in (90, 270):
            aspect = 1 / aspect
        items = [
            {"t": w["t"], "p": w["p"], "b": to_reading(w["b"], angle), "d": w["b"]} for w in by_page[page]
        ]
        current: Line | None = None
        for w in sorted(items, key=lambda w: (w["b"][1] + w["b"][3]) / 2):
            middle = (w["b"][1] + w["b"][3]) / 2
            height = w["b"][3] - w["b"][1]
            if current is not None and abs(middle - current.middle) < 0.5 * min(height, current.height):
                current.words.append(w)
            else:
                current = Line(page, aspect, [w])
                lines.append(current)
    for line in lines:
        line.words.sort(key=lambda w: w["b"][0])
    return lines


@dataclass(frozen=True)
class LabelHit:
    line: Line
    start: int  # índice da primeira palavra do rótulo na linha
    end: int  # índice depois da última

    @property
    def words(self) -> list[Word]:
        return self.line.words[self.start : self.end]

    @property
    def box(self) -> Box:
        return union(w["b"] for w in self.words)


def find_label(lines: Sequence[Line], label: str) -> list[LabelHit]:
    """Ocorrências do rótulo, palavra por palavra, sem acento nem maiúscula nem pontuação nas pontas."""
    wanted = norm_tokens(label)
    if not wanted:
        return []
    hits = []
    n = len(wanted)
    for line in lines:
        # só as palavras de verdade: um "-" solto vira token vazio e não pode quebrar o rótulo
        real = [(i, t) for i, t in enumerate(line.tokens()) if t]
        tokens = [t for _, t in real]
        for k in range(len(tokens) - n + 1):
            if tokens[k : k + n] == wanted:
                hits.append(LabelHit(line, real[k][0], real[k + n - 1][0] + 1))
    return hits


def line_matches(line: Line, phrases: Sequence[str]) -> bool:
    """A linha contém todas as frases, na ordem (cabeçalho de tabela)."""
    tokens = [t for t in line.tokens() if t]
    pos = 0
    for phrase in phrases:
        wanted = norm_tokens(phrase)
        found = next(
            (i for i in range(pos, len(tokens) - len(wanted) + 1) if tokens[i : i + len(wanted)] == wanted),
            -1,
        )
        if not wanted or found < 0:
            return False
        pos = found + len(wanted)
    return True


def line_starts_with(line: Line, phrases: Sequence[str]) -> bool:
    tokens = [t for t in line.tokens() if t]
    for phrase in phrases:
        wanted = norm_tokens(phrase)
        if wanted and tokens[: len(wanted)] == wanted:
            return True
    return False
