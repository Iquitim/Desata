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
from prodata.documents.layout import Box, Line, Word, generalize, group_lines, norm_tokens, to_reading, union
from prodata.documents.recipe import Column, FieldSpec, LabelRule, PositionRule, TableSpec
from prodata.documents.types import guess_type, normalize

_LABEL_GAP = 1.5
MIN_GAP = 0.006  # espaço vazio mínimo entre colunas, em fração da largura da página
_CURRENCY = {"r$", "rs", "us$", "$", "€"}


def field_name(label: str) -> str:
    """'Total líquido:' → 'total_liquido' (nome de coluna sem acento nem espaço)."""
    slug = re.sub(r"[^a-z0-9]+", "_", normalize(label)).strip("_")
    return slug[:60] or "campo"


def _same(a: Sequence[Word], b: Sequence[Word]) -> bool:
    return {id(w) for w in a} == {id(w) for w in b}


def _left_label(line: Line, first: int, far: bool = False) -> list[Word]:
    """Palavras grudadas à esquerda da seleção; se há uma terminada em ':', o rótulo vai até ela."""
    group: list[Word] = []
    i = first - 1
    while i >= 0 and (not group or line.gap(line.words[i], group[0]) <= _LABEL_GAP):
        if not group and not far and line.gap(line.words[i], line.words[first]) > 6:
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
    """O rótulo proposto, com o que muda de mês para mês (mês, ano, data) já como curinga (0.9.6)."""
    return generalize(" ".join(w["t"] for w in words))[0]


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
    box = union(w["b"] for w in chosen)
    page = chosen[0]["p"]
    proposals: list[dict[str, Any]] = []
    first_line = next(i for i, ln in enumerate(lines) if any(w is chosen[0] for w in ln.words))
    line = lines[first_line]
    first = next(k for k, w in enumerate(line.words) if w is chosen[0])
    # "834.086,00" marcado sem o "R$" que vem logo antes ainda é moeda
    before = normalize(line.words[first - 1]["t"]) if first > 0 else ""
    kind = guess_type(text, currency=before in _CURRENCY)
    left = _left_label(line, first)
    reach = 0.3
    if not left:
        # rótulo longe, na mesma linha, sem nada no meio (ex.: um título à esquerda e a data no canto)
        left = _left_label(line, first, far=True)
        if left:
            reach = min(1.0, round(box[0] - union(w["b"] for w in left)[2] + 0.05, 3))
    if left:
        label = _label_text(left)
        rule = LabelRule(rotulos=[label.rstrip(":").strip() or label], direcao="direita", distancia=reach)
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


def _spans(line: Line) -> list[tuple[float, float]]:
    """Trechos ocupados da linha; o "R$" fica grudado no valor que vem depois (nunca vira coluna própria)."""
    spans: list[tuple[float, float]] = []
    glue = False
    for w in line.words:
        if glue and spans:
            spans[-1] = (spans[-1][0], w["b"][2])
        else:
            spans.append((w["b"][0], w["b"][2]))
        glue = normalize(w["t"]) in _CURRENCY
    return spans


def column_gap(lines: Sequence[Line]) -> float:
    """Espaço mínimo entre colunas, medido no próprio documento: um pouco mais que o espaço comum entre palavras."""
    gaps = sorted(
        b[0] - a[1] for ln in lines for a, b in zip(_spans(ln), _spans(ln)[1:], strict=False) if b[0] > a[1]
    )
    if not gaps:
        return MIN_GAP
    space = gaps[len(gaps) // 5]  # o espaço entre palavras é dos menores vãos de uma linha
    return max(0.0025, min(MIN_GAP, space * 1.05))


def _gaps(lines: Sequence[Line], lo: float, hi: float, min_width: float) -> list[tuple[float, float]]:
    bins = 2000
    covered = [False] * bins
    for ln in lines:
        for x0, x1 in _spans(ln):
            a = max(0, int((x0 - lo) / (hi - lo) * bins))
            b = min(bins, int((x1 - lo) / (hi - lo) * bins) + 1)
            for k in range(a, b):
                covered[k] = True
    gaps, start = [], None
    for k, c in enumerate([*covered, True]):
        if not c and start is None:
            start = k
        elif c and start is not None:
            if start > 0 and k < bins:  # só espaço entre colunas, não as margens
                g0, g1 = lo + start / bins * (hi - lo), lo + k / bins * (hi - lo)
                if g1 - g0 >= min_width:
                    gaps.append((g0, g1))
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
    # cabeçalho = as linhas de cima até a primeira com número decimal (os dados); no mínimo uma
    heads = 1
    while heads < min(len(inside) - 1, 6) and not _has_numbers(inside[heads]):
        heads += 1
    header_lines, body = inside[:heads], inside[heads:]
    # a âncora é a linha com os títulos das colunas (a de mais palavras), não uma linha genérica acima dela
    # ("UNIDADE: R$ MILHÕES" se repete em várias tabelas do mesmo relatório)
    anchor = max(range(heads), key=lambda k: (len(header_lines[k].words), k))
    header_lines = header_lines[anchor:]
    heads -= anchor
    header = header_lines[0]
    gaps = _gaps(body, x0, x1, min_width=column_gap(body))
    guides = sorted(g for g in (_place_guide(gap, header) for gap in gaps) if x0 < g < x1)
    titles: list[list[str]] = [[] for _ in range(len(guides) + 1)]
    first_titles: list[list[str]] = [[] for _ in range(len(guides) + 1)]
    for n, ln in enumerate(header_lines):
        for w in ln.words:
            at = sum(1 for g in guides if g < (w["b"][0] + w["b"][2]) / 2)
            titles[at].append(w["t"])
            if n == 0:
                first_titles[at].append(w["t"])
    names, seen = [], set()
    for k, parts in enumerate(titles):
        base = field_name(" ".join(parts)) if parts else "campo"
        if base == "campo":  # sem título legível (só "*", por exemplo)
            base = f"coluna_{k + 1}"
        cand, n = base, 2
        while cand in seen:
            cand, n = f"{base}_{n}", n + 1
        seen.add(cand)
        names.append(cand)
    start = _start_column(body, guides, names)
    columns = []
    for k, col in enumerate(names):
        sample = [
            w["t"]
            for ln in body
            for w in ln.words
            if sum(1 for g in guides if g < (w["b"][0] + w["b"][2]) / 2) == k
        ]
        kind = _column_kind(sample)
        columns.append(Column(nome=col, tipo=kind))
    header_phrases = [" ".join(parts) for parts in first_titles if parts]
    spec = TableSpec(
        nome=field_name(name),
        cabecalho=header_phrases or [header.text],
        linhas_cabecalho=heads,
        colunas=columns,
        guias=guides,
        limites=(round(x0, 4), round(x1, 4)),
        coluna_inicio=start,
    )
    # RF-3735: com mais conteúdo da tabela logo abaixo da seleção, o corte é da pessoa: a tabela para onde ela soltou
    if _content_below(lines, inside[-1], spec):
        spec = spec.model_copy(update={"max_linhas": _rows_until(spec, lines, inside[-1])})
    else:
        spec = spec.model_copy(update={"fim": _end_hint(lines, inside[-1], spec)})
    return {
        "tabela": spec.model_dump(mode="json"),
        "resultado": extract_table(spec, lines).as_dict(),
        "explicacao": (
            f"{len(names)} colunas pelos espaços em branco"
            + (f"; nova linha quando “{start}” tem valor" if start else "; cada linha do PDF é uma linha")
        ),
    }


def _same_line(a: Line, b: Line) -> bool:
    return a.page == b.page and abs(a.middle - b.middle) < 1e-6


def _within(line: Line, x0: float, x1: float) -> bool:
    return any(x0 <= (w["b"][0] + w["b"][2]) / 2 <= x1 for w in line.words)


def _is_total(line: Line) -> bool:
    tokens = norm_tokens(line.text)
    return bool(tokens) and tokens[0] in {"total", "totais", "subtotal"}


def _is_content(line: Line, spec: TableSpec) -> bool:
    """A linha é da tabela: tem números, ou é a continuação de uma célula quebrada (nada na coluna que inicia
    linha). Um total, uma nota ou um rodapé não é."""
    if _is_total(line):
        return False
    if _has_numbers(line):
        return True
    if spec.coluna_inicio is None:
        return False
    k = [c.nome for c in spec.colunas].index(spec.coluna_inicio)
    lo = spec.guias[k - 1] if k > 0 else spec.limites[0]
    hi = spec.guias[k] if k < len(spec.guias) else spec.limites[1]
    inside = [w for w in line.words if spec.limites[0] <= (w["b"][0] + w["b"][2]) / 2 <= spec.limites[1]]
    return bool(inside) and not any(lo <= (w["b"][0] + w["b"][2]) / 2 < hi for w in inside)


def _content_below(lines: Sequence[Line], last: Line, spec: TableSpec) -> bool:
    """Logo abaixo da seleção, na mesma página, vem mais conteúdo da tabela?"""
    after = False
    for ln in lines:
        if _same_line(ln, last):
            after = True
            continue
        if after and _within(ln, *spec.limites):
            return ln.page == last.page and _is_content(ln, spec)
    return False


def _rows_until(spec: TableSpec, lines: Sequence[Line], last: Line) -> int:
    """Quantas linhas da tabela começam até ``last`` (as linhas quebradas contam junto com a sua)."""
    upto = []
    for ln in lines:
        upto.append(ln)
        if _same_line(ln, last):
            break
    free = spec.model_copy(update={"fim": [], "max_linhas": None})
    return max(1, len(extract_table(free, upto).linhas))


def adjust_edge(info: dict[str, Any], table: TableSpec, page: int, edge: str, pos: float) -> TableSpec:
    """Borda da tabela arrastada (RF-3735). ``pos`` é a altura na página, no espaço de leitura.

    - ``bottom``: soltar antes de uma linha de texto termina antes dela; no meio dos dados, depois de N linhas;
      abaixo da última linha da página, a tabela segue a regra de fim (ou até o fim do documento).
    - ``top``: a linha logo abaixo da borda vira o cabeçalho, com as colunas de hoje.
    """
    lines = group_lines(info["words"], info["pages"])
    lo, hi = table.limites
    on_page = [ln for ln in lines if ln.page == page and _within(ln, lo, hi)]
    if edge == "top":
        header = next((ln for ln in on_page if ln.middle >= pos), None)
        if header is None:
            raise ValueError("solte a borda de cima acima de uma linha")
        titles: list[list[str]] = [[] for _ in table.colunas]
        for w in header.words:
            middle = (w["b"][0] + w["b"][2]) / 2
            if lo <= middle <= hi:
                titles[sum(1 for g in table.guias if g < middle)].append(w["t"])
        phrases = [" ".join(t) for t in titles if t]
        return table.model_copy(update={"cabecalho": phrases or [header.text], "linhas_cabecalho": 1})
    if edge != "bottom":
        raise ValueError("borda desconhecida")
    free = table.model_copy(update={"max_linhas": None})
    rows = extract_table(free, lines).linhas
    starts = [min((w["p"], w["b"][1]) for c in r.cells for w in c.words) for r in rows]
    count = sum(1 for p, y in starts if (p, y) < (page, pos))
    below = next((ln for ln in on_page if ln.middle > pos), None)
    if (
        below is None
    ):  # depois da última linha da página: sem corte, com a regra de fim (sugerida de novo se não há)
        last = next((ln for ln in reversed(on_page) if ln.middle < pos), None)
        return free.model_copy(update={"fim": table.fim or (_end_hint(lines, last, table) if last else [])})
    if count < 1:
        raise ValueError("solte a borda de baixo depois de pelo menos uma linha da tabela")
    if not _is_content(below, table):
        return table.model_copy(update={"fim": [" ".join(below.text.split()[:2])], "max_linhas": None})
    return table.model_copy(update={"fim": [], "max_linhas": count})


_DECIMAL = re.compile(r"^[-(]?[\d.]+,\d+\)?$")
_INTEGER = re.compile(r"^[-(]?(\d{1,3}(\.\d{3})+|\d+)\)?$")  # "70.182", "(3.214)", "146"


def _has_numbers(line: Line) -> bool:
    """A linha tem número decimal ("5,22", "-60,00"): é dado, não cabeçalho."""
    return any(_DECIMAL.match(w["t"]) for w in line.words)


def _column_kind(sample: list[str]) -> Any:
    """Tipo da coluna pelos valores: moeda só se algum tiver "R$"; texto quando há palavras misturadas."""
    values = [t for t in sample if t not in {"-", "–"}]
    if not values:
        return "texto"
    money = any("R$" in t.upper() for t in values)
    numbers = [t for t in values if _DECIMAL.match(t) or _INTEGER.match(t)]
    if money and len(numbers) >= len(values) / 3:
        return "moeda"
    if len(numbers) == len(values):
        return "decimal" if any("," in t for t in numbers) else "inteiro"
    joined = " ".join(values[:3])
    kind = guess_type(joined)
    return kind if kind == "data" else "texto"


def _start_column(body: Sequence[Line], guides: Sequence[float], names: Sequence[str]) -> str | None:
    """A coluna que inicia linha (RF-3731). Toda linha com número = cada linha do PDF é uma linha da tabela.

    Senão, há linhas de continuação (texto quebrado, sem números): vale a coluna mais à esquerda que aparece em toda
    linha com números e em nenhuma de continuação. Uma coluna às vezes vazia (um sinal que só aparece quando muda)
    nunca é escolhida por isso.
    """

    def cols(ln: Line) -> set[int]:
        return {sum(1 for g in guides if g < (w["b"][0] + w["b"][2]) / 2) for w in ln.words}

    rows = [cols(ln) for ln in body if _has_numbers(ln)]
    rest = [cols(ln) for ln in body if not _has_numbers(ln)]
    if not rows or not rest:
        return None
    always = set.intersection(*rows)
    never = always - set().union(*rest)
    chosen = min(never or always, default=None)
    return names[chosen] if chosen is not None else None


def _end_hint(lines: Sequence[Line], last: Line, spec: TableSpec | None = None) -> list[str]:
    """Sugere onde a tabela termina: a linha "Total…" depois da área ou, na mesma página, a primeira linha logo
    abaixo que não é dado (uma nota ou um rodapé). A pessoa confirma ou troca."""
    after = False
    below: Line | None = None
    for ln in lines:
        if ln is last or (ln.page == last.page and abs(ln.middle - last.middle) < 1e-6):
            after = True
            continue
        if after and (ln.page > last.page or ln.middle > last.middle):
            tokens = norm_tokens(ln.text)
            if tokens and tokens[0] in {"total", "totais", "subtotal"}:
                return [" ".join(ln.text.split()[:2])]
            content = _is_content(ln, spec) if spec is not None else _has_numbers(ln)
            if below is None and ln.page == last.page and not content:
                below = ln
    if below is not None and norm_tokens(below.text):
        return [" ".join(below.text.split()[:2])]
    return []
