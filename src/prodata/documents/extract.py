"""Aplica uma extração às palavras de um documento (spec 037, RF-3721, RF-3730..3734, RF-3760).

Nada é inventado: sem candidato, o campo fica Ausente; com valores diferentes, Ambíguo (todos os candidatos voltam, com
página e caixa, para a tela destacar); achou e não converte, Inválido. Toda célula e todo valor trazem a origem
(página e caixa), que é o que permite "de onde veio" nos dois sentidos.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from prodata.documents.layout import (
    LabelHit,
    Line,
    Word,
    find_label,
    group_lines,
    line_matches,
    line_starts_with,
    union,
)
from prodata.documents.recipe import FieldSpec, LabelRule, PositionRule, Recipe, SectionRule, TableSpec
from prodata.documents.types import InvalidValueError, convert, normalize, to_json

ENCONTRADO, AUSENTE, AMBIGUO, INVALIDO, NAO_SUPORTADO = (
    "encontrado",
    "ausente",
    "ambiguo",
    "invalido",
    "nao_suportado",
)
APROVADO, REVISAR, FALHOU = "aprovado", "revisar", "falhou"
_WORD_GAP = 1.5
_EMPTY = {"-", "–", "—", "--"}  # acima disso (em alturas de linha), o espaço separa valores, não palavras


def _origin(words: Sequence[Word]) -> list[dict[str, Any]]:
    """Origem por página: [{"p": 0, "b": [...]}, ...] (uma célula pode atravessar a quebra de página)."""
    pages: dict[int, list[Sequence[float]]] = {}
    for w in words:
        pages.setdefault(w["p"], []).append(
            w["d"] if "d" in w else w["b"]
        )  # origem sempre em coordenadas de tela
    return [{"p": p, "b": [round(v, 5) for v in union(ws)]} for p, ws in sorted(pages.items())]


def _join(words: Sequence[Word]) -> str:
    return " ".join(w["t"] for w in words)


# ------------------------------------------------------------------ campos


@dataclass
class Candidate:
    texto: str
    origem: list[dict[str, Any]]
    rotulo: list[dict[str, Any]] = field(default_factory=list)
    valor: Any = None
    erro: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "texto": self.texto,
            "valor": to_json(self.valor),
            "erro": self.erro,
            "origem": self.origem,
            "rotulo": self.rotulo,
        }


@dataclass
class FieldResult:
    nome: str
    tipo: str
    obrigatorio: bool
    estado: str
    valor: Any = None
    texto: str | None = None
    candidatos: list[Candidate] = field(default_factory=list)
    motivo: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "nome": self.nome,
            "tipo": self.tipo,
            "obrigatorio": self.obrigatorio,
            "estado": self.estado,
            "valor": to_json(self.valor),
            "texto": self.texto,
            "motivo": self.motivo,
            "candidatos": [c.as_dict() for c in self.candidatos],
        }


def _right_of(hit: LabelHit, reach: float) -> list[Word]:
    line = hit.line
    after = line.words[hit.end :]
    if not after or after[0]["b"][0] - hit.box[2] > reach:
        return []
    out = [after[0]]
    for prev, nxt in pairwise(after):
        if line.gap(prev, nxt) > _WORD_GAP:
            break
        out.append(nxt)
    return out


def _below(hit: LabelHit, lines: Sequence[Line], index: dict[int, int], reach: float) -> list[Word]:
    x0, _, x1, bottom = hit.box
    margin = (x1 - x0) * 0.5
    for line in lines[index[id(hit.line)] + 1 :]:
        if line.page != hit.line.page or line.top - bottom > reach:
            break
        inside = [
            i for i, w in enumerate(line.words) if w["b"][2] >= x0 - margin and w["b"][0] <= x1 + margin
        ]
        if not inside:
            continue
        first, last = inside[0], inside[-1]
        while first > 0 and line.gap(line.words[first - 1], line.words[first]) <= _WORD_GAP:
            first -= 1
        while last < len(line.words) - 1 and line.gap(line.words[last], line.words[last + 1]) <= _WORD_GAP:
            last += 1
        return line.words[first : last + 1]
    return []


def _section(lines: Sequence[Line], rule: SectionRule) -> list[Line] | None:
    start = next(
        (i for i, ln in enumerate(lines) if any(line_starts_with(ln, [s]) for s in rule.inicio)), None
    )
    if start is None:
        return None
    block: list[Line] = []
    for line in lines[start:]:
        if block and rule.fim and line_starts_with(line, rule.fim):
            break
        block.append(line)
    return block


def _label_candidates(lines: Sequence[Line], rule: LabelRule) -> tuple[list[Candidate], int]:
    index = {id(ln): i for i, ln in enumerate(lines)}
    hits = [hit for label in rule.rotulos for hit in find_label(lines, label)]
    found = []
    for hit in hits:
        words = (
            _right_of(hit, rule.distancia)
            if rule.direcao == "direita"
            else _below(hit, lines, index, rule.distancia)
        )
        if words:
            found.append(Candidate(_join(words), _origin(words), _origin(hit.words)))
    return found, len(hits)


def _position_candidates(lines: Sequence[Line], rule: PositionRule) -> list[Candidate]:
    x0, y0, x1, y1 = rule.area
    words = [
        w
        for ln in lines
        if ln.page == rule.pagina
        for w in ln.words
        if x0 <= (w["b"][0] + w["b"][2]) / 2 <= x1 and y0 <= (w["b"][1] + w["b"][3]) / 2 <= y1
    ]
    return [Candidate(_join(words), _origin(words))] if words else []


def extract_field(spec: FieldSpec, lines: Sequence[Line]) -> FieldResult:
    result = FieldResult(spec.nome, spec.tipo, spec.obrigatorio, AUSENTE)
    rule = spec.regra
    if isinstance(rule, PositionRule):
        candidates, labels = _position_candidates(lines, rule), 0
        if not candidates:
            result.motivo = "nada escrito na área marcada"
            return result
    else:
        scope = _section(lines, rule) if isinstance(rule, SectionRule) else list(lines)
        if scope is None:
            result.motivo = "seção não encontrada"
            return result
        candidates, labels = _label_candidates(scope, rule)
        if not candidates:
            where = "à direita" if rule.direcao == "direita" else "abaixo"
            result.motivo = f"achei o rótulo, mas nada {where} dele" if labels else "rótulo não encontrado"
            return result
    for c in candidates:
        try:
            c.valor = convert(c.texto, spec.tipo)
        except InvalidValueError as exc:
            c.erro = str(exc)
    # um candidato que nem é do tipo do campo ("Equipe Técnica" para um mês/ano) não é plausível: sai, desde que
    # outro seja. Dois valores válidos e diferentes continuam Ambíguo (RF-3760).
    valid = [c for c in candidates if c.erro is None]
    if valid and len(valid) < len(candidates):
        candidates = valid
    result.candidatos = candidates
    distinct = {to_json(c.valor) if c.erro is None else ("!", normalize(c.texto)) for c in candidates}
    if len(distinct) > 1:
        result.estado = AMBIGUO
        result.motivo = f"{len(distinct)} valores diferentes"
        return result
    first = candidates[0]
    result.texto = first.texto
    if first.erro is not None:
        result.estado, result.motivo = INVALIDO, first.erro
    else:
        result.estado, result.valor = ENCONTRADO, first.valor
        if len(candidates) > 1:
            result.motivo = f"o mesmo valor em {len(candidates)} lugares"
    return result


# ------------------------------------------------------------------ tabelas


@dataclass
class Cell:
    words: list[Word] = field(default_factory=list)
    valor: Any = None
    erro: str | None = None

    @property
    def texto(self) -> str:
        return _join(self.words)

    def as_dict(self) -> dict[str, Any]:
        return {
            "texto": self.texto,
            "valor": to_json(self.valor),
            "erro": self.erro,
            "origem": _origin(self.words),
        }


@dataclass
class Row:
    cells: list[Cell]
    duvida: str | None = None
    linhas: int = 1  # quantas linhas do PDF formaram esta linha

    def as_dict(self, columns: Sequence[str]) -> dict[str, Any]:
        return {
            "celulas": {name: cell.as_dict() for name, cell in zip(columns, self.cells, strict=True)},
            "duvida": self.duvida,
            "linhas": self.linhas,
        }


@dataclass
class TableResult:
    nome: str
    colunas: list[str]
    linhas: list[Row] = field(default_factory=list)
    problema: str | None = None
    ignoradas: list[dict[str, Any]] = field(default_factory=list)  # cabeçalho repetido, exclusões, fim
    fim: str = ""  # como a tabela terminou
    cabecalho: list[dict[str, Any]] = field(
        default_factory=list
    )  # onde está o cabeçalho (a borda de cima, RF-3735)

    def as_dict(self) -> dict[str, Any]:
        return {
            "nome": self.nome,
            "colunas": self.colunas,
            "linhas": [r.as_dict(self.colunas) for r in self.linhas],
            "problema": self.problema,
            "ignoradas": self.ignoradas,
            "fim": self.fim,
            "cabecalho": self.cabecalho,
        }


def _ignored(line: Line, why: str) -> dict[str, Any]:
    return {"motivo": why, "origem": _origin(line.words)}


def _table_lines(spec: TableSpec, lines: Sequence[Line], result: TableResult) -> list[Line]:
    """Linhas da tabela: do cabeçalho até o fim, pulando cabeçalho repetido e exclusões, seguindo de página."""
    start = next((i for i, ln in enumerate(lines) if line_matches(ln, spec.cabecalho)), None)
    if start is None:
        result.problema = "não achei o cabeçalho da tabela"
        return []
    header_page = lines[start].page
    body: list[Line] = []
    extra = spec.linhas_cabecalho - 1  # as outras linhas do cabeçalho, logo abaixo da primeira
    result.cabecalho = [o for ln in lines[start : start + extra + 1] for o in _origin(ln.words)]
    skip_until = start + extra
    result.fim = "fim do documento"
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.page != lines[i - 1].page:
            if not spec.continua:
                result.fim = "fim da página"
                break
            repeated = next(
                (
                    j
                    for j in range(i, len(lines))
                    if lines[j].page == line.page and line_matches(lines[j], spec.cabecalho)
                ),
                None,
            )
            if repeated is not None:
                skip_until = repeated + extra
                result.ignoradas.append(_ignored(lines[repeated], "cabeçalho repetido"))
        if i <= skip_until:
            continue
        if spec.fim and line_starts_with(line, spec.fim):
            result.fim = "texto de fim"
            result.ignoradas.append(_ignored(line, "fim da tabela"))
            break
        if line_matches(line, spec.cabecalho):
            result.ignoradas.append(_ignored(line, "cabeçalho repetido"))
            continue
        if spec.excluir and line_starts_with(line, spec.excluir):
            result.ignoradas.append(_ignored(line, "linha excluída"))
            continue
        if (
            not spec.fim
            and body
            and body[-1].page == line.page
            and line.top - body[-1].bottom > 3 * line.height
        ):
            result.fim = "espaço grande depois da última linha"
            break
        if line.page < header_page:
            continue
        body.append(line)
    return body


def extract_table(spec: TableSpec, lines: Sequence[Line]) -> TableResult:
    names = [c.nome for c in spec.colunas]
    result = TableResult(spec.nome, names)
    lo, hi = spec.limites
    start_col = names.index(spec.coluna_inicio) if spec.coluna_inicio else None
    kinds = [c.tipo for c in spec.colunas]
    for line in _table_lines(spec, lines, result):
        cells = [Cell() for _ in names]
        for w in line.words:
            middle = (w["b"][0] + w["b"][2]) / 2
            if lo <= middle <= hi:
                cells[bisect_right(spec.guias, middle)].words.append(w)
        if not any(c.words for c in cells):
            continue
        if start_col is None or cells[start_col].words:
            if spec.max_linhas is not None and len(result.linhas) >= spec.max_linhas:
                result.fim = f"depois de {spec.max_linhas} linha(s)"  # o corte da pessoa (RF-3735)
                break
            result.linhas.append(Row(cells))
            continue
        if not result.linhas:
            result.linhas.append(Row(cells, f"começa sem valor em {names[start_col]}"))
            continue
        row = result.linhas[-1]
        row.linhas += 1
        for k, extra in enumerate(cells):
            if not extra.words:
                continue
            if row.cells[k].words and kinds[k] != "texto":
                row.duvida = f"{names[k]} tem valor em mais de uma linha"
            row.cells[k].words += extra.words
    _convert_rows(result, kinds)
    if not result.problema and not result.linhas:
        result.problema = "nenhuma linha entre o cabeçalho e o fim"
    return result


def _convert_rows(result: TableResult, kinds: Sequence[Any]) -> None:
    for row in result.linhas:
        for cell, kind in zip(row.cells, kinds, strict=True):
            if not cell.words or cell.texto.strip() in _EMPTY:  # "-" em relatório é célula vazia, não erro
                continue
            try:
                cell.valor = convert(cell.texto, kind)
            except InvalidValueError as exc:
                cell.erro = str(exc)
                row.duvida = row.duvida or "valor que não converte"


# ------------------------------------------------------------------ documento


@dataclass
class DocResult:
    estado: str
    campos: list[FieldResult]
    tabelas: list[TableResult]
    motivo: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "estado": self.estado,
            "motivo": self.motivo,
            "campos": [f.as_dict() for f in self.campos],
            "tabelas": [t.as_dict() for t in self.tabelas],
        }


def _doc_state(fields: Sequence[FieldResult], tables: Sequence[TableResult]) -> tuple[str, str]:
    required = [f.nome for f in fields if f.obrigatorio and f.estado != ENCONTRADO]
    if required:
        return FALHOU, "obrigatório sem valor: " + ", ".join(required)
    issues = [f.nome for f in fields if f.estado != ENCONTRADO]
    issues += [t.nome for t in tables if t.problema or any(r.duvida for r in t.linhas)]
    if issues:
        return REVISAR, "conferir: " + ", ".join(issues)
    return APROVADO, ""


def extract(recipe: Recipe, info: dict[str, Any]) -> DocResult:
    """``info`` é o que o leitor devolve: ``{"pages": [...], "words": [...]}``."""
    lines = group_lines(info["words"], info["pages"])
    fields = [extract_field(f, lines) for f in recipe.campos]
    tables = [extract_table(t, lines) for t in recipe.tabelas]
    state, why = _doc_state(fields, tables)
    return DocResult(state, fields, tables, why)


def unsupported(recipe: Recipe, why: str) -> DocResult:
    """Documento que não dá para ler (escaneado, protegido, quebrado): tudo Não suportado, documento Falhou."""
    fields = [FieldResult(f.nome, f.tipo, f.obrigatorio, NAO_SUPORTADO, motivo=why) for f in recipe.campos]
    tables = [TableResult(t.nome, [c.nome for c in t.colunas], problema=why) for t in recipe.tabelas]
    return DocResult(FALHOU, fields, tables, why)
