"""Sugestões a partir do que a pessoa marcou no PDF (spec 037, RF-3720, RF-3721, RF-3730, RF-3731).

Marcar um valor propõe nome, tipo e **como encontrar** ("à direita de 'Total líquido:'"), e a proposta é conferida no
próprio documento: se a regra não acha exatamente o que foi marcado, o Desata tenta a próxima (abaixo, e por fim a
posição fixa, marcada como frágil). Marcar uma área propõe tabela: cabeçalho, guias pelos espaços em branco e a
coluna que inicia linha.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from prodata.documents.extract import ENCONTRADO, extract_field, extract_table
from prodata.documents.layout import Box, Line, Word, group_lines, norm_tokens, to_reading, union
from prodata.documents.recipe import Column, FieldSpec, LabelRule, PositionRule, TableSpec
from prodata.documents.types import guess_type, normalize

_LABEL_GAP = 1.5
_CURRENCY = {"r$", "rs", "us$", "$", "€"}


def field_name(label: str) -> str:
    """'Total líquido:' → 'total_liquido' (nome de coluna sem acento nem espaço)."""
    slug = re.sub(r"[^a-z0-9]+", "_", normalize(label)).strip("_")
    return slug[:60] or "campo"


def _same(a: Sequence[Word], b: Sequence[Word]) -> bool:
    return {id(w) for w in a} == {id(w) for w in b}


def _left_label(line: Line, first: int) -> list[Word]:
    """Palavras grudadas à esquerda da seleção; se há uma terminada em ':', o rótulo vai até ela."""
    group: list[Word] = []
    i = first - 1
    while i >= 0 and (not group or line.gap(line.words[i], group[0]) <= _LABEL_GAP):
        if not group and line.gap(line.words[i], line.words[first]) > 6:
            break
        group.insert(0, line.words[i])
        i -= 1
    colon = max((k for k, w in enumerate(group) if w["t"].endswith(":")), default=None)
    if colon is not None:
        return group[: colon + 1]
    while group and normalize(group[-1]["t"]) in _CURRENCY:
        group.pop()
    return group


def _above_label(lines: Sequence[Line], idx: int, box: Box) -> list[Word]:
    line = lines[idx]
    for prev in reversed(lines[:idx]):
        if prev.page != line.page or line.top - prev.bottom > 3 * line.height:
            return []
        over = [w for w in prev.words if w["b"][2] >= box[0] and w["b"][0] <= box[2]]
        if over:
            return over
    return []


def _label_text(words: Sequence[Word]) -> str:
    return " ".join(w["t"] for w in words)


def _proposal(name: str, kind: str, rule: Any, why: str, fragile: bool = False) -> dict[str, Any]:
    spec = FieldSpec(nome=name, tipo=kind, regra=rule)
    return {"campo": spec, "explicacao": why, "fragil": fragile}


def suggest_field(info: dict[str, Any], selected: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """``selected``: palavras marcadas (como vieram do leitor). Devolve a proposta conferida e o resultado nela."""
    lines = group_lines(info["words"], info["pages"])
    picked = {(w["p"], tuple(w["b"])) for w in selected}  # caixas de tela, como a tela recebeu
    chosen = [w for ln in lines for w in ln.words if (w["p"], tuple(w["d"])) in picked]
    if not chosen:
        raise ValueError("nada marcado")
    text = " ".join(w["t"] for w in chosen)
    kind = guess_type(text)
    box = union(w["b"] for w in chosen)
    page = chosen[0]["p"]
    proposals: list[dict[str, Any]] = []
    first_line = next(i for i, ln in enumerate(lines) if any(w is chosen[0] for w in ln.words))
    line = lines[first_line]
    left = _left_label(line, next(k for k, w in enumerate(line.words) if w is chosen[0]))
    if left:
        label = _label_text(left)
        rule = LabelRule(rotulos=[label.rstrip(":").strip() or label], direcao="direita")
        proposals.append(_proposal(field_name(label), kind, rule, f"à direita de “{label.rstrip(':')}”"))
    above = _above_label(lines, first_line, box)
    if above:
        label = _label_text(above)
        rule = LabelRule(rotulos=[label.rstrip(":").strip() or label], direcao="abaixo")
        proposals.append(_proposal(field_name(label), kind, rule, f"abaixo de “{label.rstrip(':')}”"))
    pad = 0.004
    area = (max(0.0, box[0] - pad), max(0.0, box[1] - pad), min(1.0, box[2] + pad), min(1.0, box[3] + pad))
    fallback_name = field_name(proposals[0]["campo"].nome if proposals else "campo")
    proposals.append(
        _proposal(
            fallback_name,
            kind,
            PositionRule(pagina=page, area=area),
            f"na mesma posição da página {page + 1}: se o layout mudar, o valor some ou vem errado",
            fragile=True,
        )
    )
    for prop in proposals:
        result = extract_field(prop["campo"], lines)
        hit = result.candidatos[0] if result.candidatos else None
        exact = hit is not None and normalize(hit.texto).endswith(normalize(text))
        if result.estado == ENCONTRADO and exact:
            return {**prop, "campo": prop["campo"].model_dump(mode="json"), "resultado": result.as_dict()}
    last = proposals[-1]
    return {
        **last,
        "campo": last["campo"].model_dump(mode="json"),
        "resultado": extract_field(last["campo"], lines).as_dict(),
    }


# ------------------------------------------------------------------ tabela


def _gaps(lines: Sequence[Line], lo: float, hi: float, min_width: float) -> list[tuple[float, float]]:
    bins = 1000
    covered = [False] * bins
    for ln in lines:
        for w in ln.words:
            a = max(0, int((w["b"][0] - lo) / (hi - lo) * bins))
            b = min(bins, int((w["b"][2] - lo) / (hi - lo) * bins) + 1)
            for k in range(a, b):
                covered[k] = True
    gaps, start = [], None
    for k, c in enumerate([*covered, True]):
        if not c and start is None:
            start = k
        elif c and start is not None:
            if start > 0 and k < bins:  # só espaço entre colunas, não as margens
                x0, x1 = lo + start / bins * (hi - lo), lo + k / bins * (hi - lo)
                if x1 - x0 >= min_width:
                    gaps.append((x0, x1))
            start = None
    return gaps


def _place_guide(gap: tuple[float, float], header: Line) -> float:
    """Meio do maior pedaço do espaço que não corta palavra do cabeçalho."""
    pieces = [gap]
    for w in header.words:
        nxt = []
        for a, b in pieces:
            if w["b"][2] <= a or w["b"][0] >= b:
                nxt.append((a, b))
                continue
            if w["b"][0] > a:
                nxt.append((a, w["b"][0]))
            if w["b"][2] < b:
                nxt.append((w["b"][2], b))
        pieces = nxt
    a, b = max(pieces, key=lambda p: p[1] - p[0]) if pieces else gap
    return round((a + b) / 2, 4)


def suggest_table(
    info: dict[str, Any], page: int, area: Sequence[float], name: str = "tabela"
) -> dict[str, Any]:
    """Área marcada → tabela proposta (cabeçalho = primeira linha, guias pelos espaços, coluna que inicia linha)."""
    angle = int(info["pages"][page].get("t", 0)) if page < len(info["pages"]) else 0
    x0, y0, x1, y1 = to_reading(area, angle)  # a área vem da tela
    lines = group_lines(info["words"], info["pages"])
    inside = []
    for ln in lines:
        words = [w for w in ln.words if x0 <= (w["b"][0] + w["b"][2]) / 2 <= x1]
        if ln.page == page and words and y0 <= ln.middle <= y1:
            inside.append(Line(ln.page, ln.aspect, words))
    if len(inside) < 2:
        raise ValueError("marque o cabeçalho e ao menos uma linha")
    header, body = inside[0], inside[1:]
    guides = [_place_guide(g, header) for g in _gaps(body, x0, x1, min_width=0.012)]
    guides = sorted(g for g in guides if x0 < g < x1)
    titles: list[list[str]] = [[] for _ in range(len(guides) + 1)]
    for w in header.words:
        middle = (w["b"][0] + w["b"][2]) / 2
        titles[sum(1 for g in guides if g < middle)].append(w["t"])
    names, seen = [], set()
    for k, parts in enumerate(titles):
        base = field_name(" ".join(parts)) if parts else f"coluna_{k + 1}"
        cand, n = base, 2
        while cand in seen:
            cand, n = f"{base}_{n}", n + 1
        seen.add(cand)
        names.append(cand)
    filled = [0] * len(names)
    for ln in body:
        cols = {sum(1 for g in guides if g < (w["b"][0] + w["b"][2]) / 2) for w in ln.words}
        for c in cols:
            filled[c] += 1
    counts = [c for c in filled if c]
    start = None
    if counts and min(counts) < max(counts):
        start = names[next(k for k, c in enumerate(filled) if c == min(counts))]
    columns = []
    for k, col in enumerate(names):
        sample = []
        for ln in body:
            sample += [
                w["t"] for w in ln.words if sum(1 for g in guides if g < (w["b"][0] + w["b"][2]) / 2) == k
            ]
        kind = guess_type(" ".join(sample[:3])) if sample else "texto"
        columns.append(
            Column(nome=col, tipo=kind if kind in ("moeda", "inteiro", "decimal", "data") else "texto")
        )
    header_phrases = [" ".join(titles[k]) for k in range(len(titles)) if titles[k]]
    spec = TableSpec(
        nome=field_name(name),
        cabecalho=header_phrases or [header.text],
        colunas=columns,
        guias=guides,
        limites=(round(x0, 4), round(x1, 4)),
        coluna_inicio=start,
        fim=_end_hint(lines, inside[-1]),
    )
    return {
        "tabela": spec.model_dump(mode="json"),
        "resultado": extract_table(spec, lines).as_dict(),
        "explicacao": (
            f"{len(names)} colunas pelos espaços em branco"
            + (f"; nova linha quando “{start}” tem valor" if start else "; cada linha do PDF é uma linha")
        ),
    }


def _end_hint(lines: Sequence[Line], last: Line) -> list[str]:
    """Sugere como fim a primeira linha que começa com 'Total' depois da área (a pessoa confirma ou troca)."""
    after = False
    for ln in lines:
        if ln is last or (ln.page == last.page and abs(ln.middle - last.middle) < 1e-6):
            after = True
            continue
        if after and (ln.page > last.page or ln.middle > last.middle):
            tokens = norm_tokens(ln.text)
            if tokens and tokens[0] in {"total", "totais", "subtotal"}:
                return [" ".join(ln.text.split()[:2])]
    return []
