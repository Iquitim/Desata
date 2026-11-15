"""Cadastro dos leitores de PDF (spec 037): fontes, extrações versionadas, correções e a leitura das saídas."""

from __future__ import annotations

import copy
import fnmatch
import getpass
import hashlib
import json
import os
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import ValidationError

from prodata.documents.cache import DocumentCache
from prodata.documents.extract import APROVADO, FALHOU, REVISAR
from prodata.documents.outputs import DocRun, apply_corrections, build_outputs, stop_message
from prodata.documents.recipe import Recipe
from prodata.documents.sources import (
    MAX_FILES,
    MAX_SOURCES,
    Correction,
    PdfSource,
    PdfStatus,
    _slug,
    check_pattern,
    outputs_of,
)
from prodata.documents.types import TYPE_LABELS, InvalidValueError, convert
from prodata.errors import ConflictError, InvalidInputError, NotFoundError

# ------------------------------------------------------------------ cadastro


def _read_json(path: Path, what: str) -> Any:
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InvalidInputError(f"Lista de {what} corrompida: {path}") from exc


def _write_json(path: Path, items: list[dict[str, Any]]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class PdfStore:
    def __init__(self, base: Path) -> None:
        """``base``: o caminho da pasta de dados enviados; os cadastros ficam ao lado dela."""
        self._sources_file = base.with_name(base.name + "_pdfs.json")
        self._recipes_file = base.with_name(base.name + "_extracoes.json")
        self._fixes_file = base.with_name(base.name + "_pdf_correcoes.json")
        self.uploads = base.with_name(base.name + "_pdfs")
        self._cache_dir = base.with_name(base.name + "_pdf_cache")
        self._lock = threading.RLock()
        self._cache: DocumentCache | None = None
        self.summaries: dict[str, tuple[dict[str, int], datetime]] = {}

    # leitura isolada sob demanda: o processo do leitor só sobe quando um PDF é aberto
    @property
    def cache(self) -> DocumentCache:
        if self._cache is None:
            from prodata.documents.worker import PdfWorker

            self._cache = DocumentCache(self._cache_dir, PdfWorker())
        return self._cache

    def close(self) -> None:
        if self._cache is not None:
            self._cache.worker.close()

    # ---------------------------------------------------------- fontes

    def _sources(self) -> dict[str, PdfSource]:
        try:
            return {
                s.id: s for s in (PdfSource.model_validate(i) for i in _read_json(self._sources_file, "PDFs"))
            }
        except (ValidationError, TypeError) as exc:
            raise InvalidInputError(f"Lista de PDFs corrompida: {self._sources_file}") from exc

    def _save_sources(self, sources: dict[str, PdfSource]) -> None:
        items = [s.model_dump(mode="json") for s in sorted(sources.values(), key=lambda s: s.name.lower())]
        _write_json(self._sources_file, items)

    def all_sources(self) -> list[PdfSource]:
        return sorted(self._sources().values(), key=lambda s: s.name.lower())

    def get(self, source_id: str) -> PdfSource:
        found = self._sources().get(source_id)
        if found is None:
            raise NotFoundError(
                f"O leitor de PDF '{source_id}' não está cadastrado neste computador. Cadastre na vista Dados."
            )
        return found

    def _check_path(self, source: PdfSource) -> PdfSource:
        path = Path(source.path.strip())
        if not path.is_absolute():
            raise InvalidInputError("Informe o caminho completo, como D:\\Relatorios\\outubro.pdf.")
        if source.mode == "arquivo":
            if path.suffix.lower() != ".pdf":
                raise InvalidInputError("Escolha um arquivo .pdf.")
            if not path.is_file():
                raise NotFoundError(f"Arquivo não encontrado: {path}")
        elif not path.is_dir():
            raise NotFoundError(f"A pasta não existe: {path}")
        examples = []
        for raw in source.examples:
            ex = Path(raw.strip())
            if not ex.is_absolute() or ex.suffix.lower() != ".pdf":
                raise InvalidInputError(f"Exemplo inválido: {raw}. Use o caminho completo de um .pdf.")
            examples.append(str(ex))
        return source.model_copy(
            update={"path": str(path), "pattern": check_pattern(source.pattern), "examples": examples}
        )

    def save(self, source: PdfSource, previous: str | None = None) -> PdfSource:
        clean = self._check_path(source)
        with self._lock:
            sources = self._sources()
            if previous:
                old = sources.get(previous)
                if old is None:
                    raise NotFoundError("Este leitor de PDF não existe mais.")
                clean = clean.model_copy(
                    update={
                        "id": previous,
                        "stored": old.stored and clean.path == old.path,
                        "added": old.added,
                        "left_out": old.left_out,
                    }
                )
            else:
                if len(sources) >= MAX_SOURCES:
                    raise InvalidInputError(f"O limite é de {MAX_SOURCES} leitores de PDF.")
                base = clean.id or _slug(clean.name, "pdf")
                new_id, n = base, 2
                while new_id in sources:
                    new_id, n = f"{base}_{n}", n + 1
                # fonte nova só traz cópias que o próprio programa guardou (Duplicar); caminho de fora não entra
                own = [p for p in clean.added if Path(p).parent == self.uploads]
                clean = clean.model_copy(update={"id": new_id, "added": own})
            if any(s.id != clean.id and s.name.casefold() == clean.name.casefold() for s in sources.values()):
                raise ConflictError(f"Já existe um leitor de PDF chamado '{clean.name}'.")
            if clean.recipe and clean.recipe not in self._recipes():
                raise NotFoundError("A extração escolhida não existe mais.")
            sources[clean.id] = clean
            self._save_sources(sources)
        return clean

    def store_upload(self, filename: str, data: bytes, taken: set[str] | None = None) -> Path:
        """Cópia enviada: guardada pelo programa, com nome seguro e sem sobrescrever outra.

        ``taken``: nomes (minúsculos) já usados na fonte; a cópia ganha outro nome para não confundir documentos.
        """
        from prodata.documents.reader import MAX_BYTES

        if not data:
            raise InvalidInputError("Arquivo vazio.")
        if len(data) > MAX_BYTES:
            raise InvalidInputError(f"O PDF passa do limite de {MAX_BYTES // 2**20} MB.")
        if not data.startswith(b"%PDF"):
            raise InvalidInputError("Este arquivo não é um PDF.")
        self.uploads.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^\w.-]+", "_", Path(filename.replace("\\", "/")).stem, flags=re.UNICODE).strip("._")
        target = self.uploads / f"{stem[:80] or 'documento'}.pdf"
        n = 2
        while target.exists() or target.name.lower() in (taken or set()):
            target = self.uploads / f"{stem[:80] or 'documento'}_{n}.pdf"
            n += 1
        target.write_bytes(data)
        return target

    def delete(self, source_id: str) -> None:
        """Esquece a fonte e as correções dela. A cópia enviada é apagada; arquivo vinculado ou pasta ficam intactos.

        A extração continua na lista de extrações salvas (RF-3705): é excluída só quando a pessoa pede.
        """
        with self._lock:
            sources = self._sources()
            gone = sources.pop(source_id, None)
            if gone is None:
                raise NotFoundError("Este leitor de PDF não existe mais.")
            self._save_sources(sources)
            if gone.stored:
                Path(gone.path).unlink(missing_ok=True)
            for raw in gone.added:
                Path(raw).unlink(missing_ok=True)
            fixes = [c for c in self._fixes() if c.source != source_id]
            _write_json(self._fixes_file, [c.model_dump(mode="json") for c in fixes])
        self.summaries.pop(source_id, None)

    def duplicate(self, source_id: str, name: str | None = None) -> PdfSource:
        """Outra fonte com a mesma extração (RF-3704), para apontar para outro arquivo ou pasta."""
        original = self.get(source_id)
        names = {s.name.casefold() for s in self.all_sources()}
        base = (name or f"{original.name} (cópia)").strip()
        candidate, n = base, 2
        while candidate.casefold() in names:
            candidate, n = f"{base} {n}", n + 1
        copy = original.model_copy(update={"id": "", "name": candidate, "stored": False})
        if original.stored:  # a cópia precisa do próprio arquivo: apagar uma não pode levar o da outra
            stored = self.store_upload(Path(original.path).name, Path(original.path).read_bytes())
            copy = copy.model_copy(update={"path": str(stored), "stored": True})
        added = []
        for raw in original.added:
            if Path(raw).is_file():
                added.append(str(self.store_upload(Path(raw).name, Path(raw).read_bytes())))
        return self.save(copy.model_copy(update={"added": added}))

    # ---------------------------------------------------------- extrações

    def _recipes(self) -> dict[str, Recipe]:
        try:
            return {
                r.id: r
                for r in (Recipe.model_validate(i) for i in _read_json(self._recipes_file, "extrações"))
            }
        except (ValidationError, TypeError) as exc:
            raise InvalidInputError(f"Lista de extrações corrompida: {self._recipes_file}") from exc

    def _save_recipes(self, recipes: dict[str, Recipe]) -> None:
        _write_json(self._recipes_file, [r.model_dump(mode="json") for r in recipes.values()])

    def recipe_of(self, source: PdfSource) -> Recipe | None:
        return self._recipes().get(source.recipe) if source.recipe else None

    def save_recipe(self, source_id: str, recipe: Recipe) -> Recipe:
        """Guarda a extração da fonte. Mudou o que muda o resultado: a revisão sobe (RF-3783)."""
        with self._lock:
            source = self.get(source_id)
            recipes = self._recipes()
            rid = source.recipe or _slug(source.name, "extracao")
            if not source.recipe:
                base, n = rid, 2
                while rid in recipes:
                    rid, n = f"{base}_{n}", n + 1
            old = recipes.get(rid)
            revision = old.revisao if old else 1
            if old and old.digest() != recipe.digest():
                revision += 1
            saved = recipe.model_copy(
                update={"id": rid, "revisao": revision, "nome": recipe.nome or source.name}
            )
            saved = Recipe.model_validate(saved.model_dump())  # valida de novo, com o id final
            recipes[rid] = saved
            self._save_recipes(recipes)
            if source.recipe != rid:
                sources = self._sources()
                sources[source_id] = source.model_copy(update={"recipe": rid})
                self._save_sources(sources)
        self.summaries.pop(source_id, None)
        return saved

    # ---------------------------------------------------------- extrações salvas (RF-3705)

    def recipe_library(self) -> list[dict[str, Any]]:
        """Todas as extrações, com o que tiram e as fontes que usam cada uma."""
        sources = self.all_sources()
        return [
            {
                "id": r.id,
                "nome": r.nome,
                "revisao": r.revisao,
                "campos": [f.nome for f in r.campos],
                "tabelas": [t.nome for t in r.tabelas],
                "fontes": [{"id": s.id, "name": s.name} for s in sources if s.recipe == r.id],
            }
            for r in sorted(self._recipes().values(), key=lambda r: r.nome.casefold())
        ]

    def get_recipe(self, recipe_id: str) -> Recipe:
        found = self._recipes().get(recipe_id)
        if found is None:
            raise NotFoundError("Esta extração não existe mais.")
        return found

    def _attach(self, source_id: str, recipe_id: str) -> None:
        sources = self._sources()
        if source_id not in sources:
            raise NotFoundError("Este leitor de PDF não existe mais.")
        sources[source_id] = sources[source_id].model_copy(update={"recipe": recipe_id})
        self._save_sources(sources)
        self.summaries.pop(source_id, None)

    def use_recipe(self, source_id: str, recipe_id: str) -> PdfSource:
        """A fonte passa a usar uma extração que já existe (compartilhada com as outras que a usam)."""
        with self._lock:
            self.get_recipe(recipe_id)
            self._attach(source_id, recipe_id)
        return self.get(source_id)

    def _new_recipe(self, recipe: Recipe, name: str) -> Recipe:
        recipes = self._recipes()
        names = {r.nome.casefold() for r in recipes.values()}
        label, n = name.strip()[:120] or "Extração", 2
        base = label
        while label.casefold() in names:
            label, n = f"{base} ({n})", n + 1
        rid, n = _slug(label, "extracao"), 2
        base_id = rid
        while rid in recipes:
            rid, n = f"{base_id}_{n}", n + 1
        fresh = Recipe.model_validate(
            {**recipe.model_dump(mode="json"), "id": rid, "nome": label, "revisao": 1}
        )
        recipes[rid] = fresh
        self._save_recipes(recipes)
        return fresh

    def fork_recipe(self, source_id: str, name: str | None = None) -> Recipe:
        """Copia a extração da fonte como uma nova, independente, e a fonte passa a usar a cópia."""
        with self._lock:
            source = self.get(source_id)
            current = self.recipe_of(source)
            if current is None:
                raise InvalidInputError("Esta fonte ainda não tem extração para copiar.")
            fresh = self._new_recipe(current, name or f"{current.nome} (cópia)")
            self._attach(source_id, fresh.id)
        return fresh

    def import_recipe(self, payload: Any, source_id: str | None = None) -> Recipe:
        """Extração vinda de um arquivo exportado. Ganha id novo; nada do arquivo vira caminho ou segredo."""
        data = (
            payload.get("extracao")
            if isinstance(payload, dict) and payload.get("tipo") == EXPORT_KIND
            else payload
        )
        try:
            recipe = Recipe.model_validate({**(data or {}), "id": "importada", "revisao": 1})
        except (ValidationError, TypeError) as exc:
            raise InvalidInputError("Este arquivo não é uma extração de PDF válida.") from exc
        with self._lock:
            fresh = self._new_recipe(recipe, recipe.nome)
            if source_id:
                self._attach(source_id, fresh.id)
        return fresh

    def export_recipe(self, recipe_id: str) -> dict[str, Any]:
        recipe = self.get_recipe(recipe_id)
        body = recipe.model_dump(mode="json", exclude={"id"})
        return {"tipo": EXPORT_KIND, "versao": 1, "extracao": body}

    def delete_recipe(self, recipe_id: str, force: bool = False) -> list[str]:
        """Exclui a extração. Se alguma fonte a usa, só com ``force``: elas voltam a rascunho. Devolve quais."""
        with self._lock:
            recipes = self._recipes()
            if recipe_id not in recipes:
                raise NotFoundError("Esta extração não existe mais.")
            sources = self._sources()
            users = [s for s in sources.values() if s.recipe == recipe_id]
            if users and not force:
                names = ", ".join(s.name for s in users)
                raise ConflictError(f"Esta extração é usada por {len(users)} fonte(s): {names}.")
            for s in users:
                sources[s.id] = s.model_copy(update={"recipe": ""})
                self.summaries.pop(s.id, None)
            if users:
                self._save_sources(sources)
            recipes.pop(recipe_id)
            self._save_recipes(recipes)
        return [s.name for s in users]

    # ---------------------------------------------------------- arquivos

    def files_of(self, source: PdfSource) -> list[Path]:
        """Os documentos que entram nos dados: os do arquivo ou da pasta, mais os somados, menos os tirados."""
        out = {name.lower() for name in source.left_out}
        return [p for p in self._all_files(source) if p.name.lower() not in out]

    def left_out_files(self, source: PdfSource) -> list[Path]:
        """Tirados da fonte e ainda no disco: aparecem em "Fora da fonte", para trazer de volta (RF-3706)."""
        out = {name.lower() for name in source.left_out}
        try:
            return [p for p in self._all_files(source) if p.name.lower() in out]
        except NotFoundError, InvalidInputError:
            return []

    def _all_files(self, source: PdfSource) -> list[Path]:
        files = self._base_files(source)
        names = {p.name.lower() for p in files}
        for raw in source.added:
            p = Path(raw)
            if p.is_file() and p.name.lower() not in names:
                files.append(p)
                names.add(p.name.lower())
        if len(files) > MAX_FILES:
            raise InvalidInputError(f"A fonte tem {len(files)} PDFs: o limite é {MAX_FILES}.")
        return files

    def _base_files(self, source: PdfSource) -> list[Path]:
        path = Path(source.path)
        if source.mode == "arquivo":
            if not path.is_file():
                raise NotFoundError(f"O PDF não foi encontrado: {path}. Ele foi movido ou renomeado?")
            return [path]
        if not path.is_dir():
            raise NotFoundError(f"A pasta não existe: {path}. Ela foi movida ou renomeada?")
        wanted = check_pattern(source.pattern).lower()
        found = sorted(
            (
                p
                for p in path.iterdir()
                if p.is_file() and p.suffix.lower() == ".pdf" and fnmatch.fnmatch(p.name.lower(), wanted)
            ),
            key=lambda p: p.name.lower(),
        )
        if len(found) > MAX_FILES:
            raise InvalidInputError(
                f"{len(found)} PDFs casam com '{source.pattern}': o limite é {MAX_FILES}. Use um padrão mais específico."
            )
        return found

    def documents(self, source: PdfSource) -> list[dict[str, Any]]:
        """Os documentos da fonte e os exemplos (que não entram nos dados), com chave estável."""
        out = []
        added = set(source.added)
        for p in self.files_of(source):
            out.append({"key": p.name, "name": p.name, "example": False, "path": p, "added": str(p) in added})
        for raw in source.examples:
            p = Path(raw)
            out.append(
                {
                    "key": f"exemplo:{p.name}",
                    "name": p.name,
                    "example": True,
                    "path": p,
                    "missing": not p.is_file(),
                }
            )
        return out

    def document_path(self, source: PdfSource, key: str) -> Path:
        for doc in self.documents(source):
            if doc["key"] == key:
                path: Path = doc["path"]
                if not path.is_file():
                    raise NotFoundError(f"O PDF não foi encontrado: {path}")
                return path
        raise NotFoundError("Este documento não faz mais parte da fonte.")

    def status(self, source: PdfSource) -> PdfStatus:
        recipe = self.recipe_of(source)
        st = PdfStatus(
            draft=not recipe or not (recipe.campos or recipe.tabelas),
            revision=recipe.revisao if recipe else 0,
            fields=len(recipe.campos) if recipe else 0,
            tables=len(recipe.tabelas) if recipe else 0,
            outputs=outputs_of(recipe),
        )
        try:
            st.files = len(self.files_of(source))
            st.left_out = len(self.left_out_files(source))
        except NotFoundError as exc:
            st.missing, st.error = True, str(exc)
        except InvalidInputError as exc:
            st.error = str(exc)
        known = self.summaries.get(source.id)
        if known:
            st.summary, st.checked_at = known
        return st

    # ---------------------------------------------------------- documentos um a um (RF-3706)

    def _source_for_update(self, source_id: str) -> tuple[dict[str, PdfSource], PdfSource]:
        sources = self._sources()
        found = sources.get(source_id)
        if found is None:
            raise NotFoundError("Este leitor de PDF não existe mais.")
        return sources, found

    def leave_out(self, source_id: str, name: str) -> bool:
        """Tira um documento da fonte. Arquivo da pessoa: só deixa de entrar (volta quando ela quiser). Cópia guardada
        pelo programa: é apagada, com as correções dela. Devolve True quando apagou a cópia."""
        with self._lock:
            sources, source = self._source_for_update(source_id)
            files = self.files_of(source)
            target = next((p for p in files if p.name == name), None)
            if target is None:
                raise NotFoundError("Este documento não faz mais parte da fonte.")
            if len(files) == 1:
                raise InvalidInputError(
                    "A fonte precisa de pelo menos um PDF. Para não usá-la mais, exclua a fonte."
                )
            removed = str(target) in source.added
            if removed:
                sources[source_id] = source.model_copy(
                    update={"added": [a for a in source.added if a != str(target)]}
                )
            else:
                sources[source_id] = source.model_copy(update={"left_out": [*source.left_out, target.name]})
            self._save_sources(sources)
            if removed:
                target.unlink(missing_ok=True)
                fixes = [
                    c for c in self._fixes() if not (c.source == source_id and c.documento == target.name)
                ]
                _write_json(self._fixes_file, [c.model_dump(mode="json") for c in fixes])
        self.summaries.pop(source_id, None)
        return removed

    def bring_back(self, source_id: str, name: str) -> None:
        with self._lock:
            sources, source = self._source_for_update(source_id)
            kept = [n for n in source.left_out if n.lower() != name.lower()]
            if len(kept) == len(source.left_out):
                raise NotFoundError("Este documento já está na fonte.")
            sources[source_id] = source.model_copy(update={"left_out": kept})
            self._save_sources(sources)
        self.summaries.pop(source_id, None)

    def add_files(self, source_id: str, files: list[tuple[str, bytes]]) -> list[str]:
        """Soma PDFs à fonte: o programa guarda uma cópia de cada; a pasta da pessoa não é tocada."""
        if not files:
            raise InvalidInputError("Escolha pelo menos um PDF.")
        with self._lock:
            _, source = self._source_for_update(source_id)
            current = self._all_files(source)
            if len(current) + len(files) > MAX_FILES:
                raise InvalidInputError(f"A fonte passaria de {MAX_FILES} PDFs.")
            taken = {p.name.lower() for p in current} | {n.lower() for n in source.left_out}
            stored: list[Path] = []
            try:
                for filename, data in files:
                    path = self.store_upload(filename, data, taken)
                    taken.add(path.name.lower())
                    stored.append(path)
            except Exception:
                for path in stored:  # tudo ou nada: um arquivo ruim não deixa metade somada
                    path.unlink(missing_ok=True)
                raise
            sources, source = self._source_for_update(source_id)
            sources[source_id] = source.model_copy(update={"added": [*source.added, *map(str, stored)]})
            self._save_sources(sources)
        self.summaries.pop(source_id, None)
        return [p.name for p in stored]

    # ---------------------------------------------------------- correções

    def _fixes(self) -> list[Correction]:
        try:
            return [Correction.model_validate(i) for i in _read_json(self._fixes_file, "correções")]
        except (ValidationError, TypeError) as exc:
            raise InvalidInputError(f"Lista de correções corrompida: {self._fixes_file}") from exc

    def corrections(self, source_id: str) -> list[Correction]:
        return [c for c in self._fixes() if c.source == source_id]

    def add_correction(self, source_id: str, doc_key: str, field_name: str, value: str) -> Correction:
        source = self.get(source_id)
        recipe = self.recipe_of(source)
        spec = next((f for f in recipe.campos if f.nome == field_name), None) if recipe else None
        if spec is None:
            raise NotFoundError(f"O campo '{field_name}' não existe nesta extração.")
        try:
            convert(value, spec.tipo)
        except InvalidValueError as exc:
            raise InvalidInputError(f"O valor não vale como {TYPE_LABELS[spec.tipo]}: {exc}.") from None
        path = self.document_path(source, doc_key)
        if doc_key.startswith("exemplo:"):
            raise InvalidInputError(
                "Exemplos servem só para testar a extração; corrija um documento da fonte."
            )
        current = self.cache.extract(path, recipe)  # type: ignore[arg-type]
        item: dict[str, Any] = next((f for f in current["campos"] if f["nome"] == field_name), {})
        fix = Correction(
            source=source_id,
            documento=path.name,
            assinatura=current["assinatura"],
            campo=field_name,
            valor=value.strip(),
            original=item.get("texto"),
            estado_original=item.get("estado", ""),
            quem=_who(),
        )
        with self._lock:
            fixes = [
                c
                for c in self._fixes()
                if not (c.source == source_id and c.documento == fix.documento and c.campo == field_name)
            ]
            fixes.append(fix)
            _write_json(self._fixes_file, [c.model_dump(mode="json") for c in fixes])
        self.summaries.pop(source_id, None)
        return fix

    def remove_correction(self, source_id: str, correction_id: str) -> None:
        with self._lock:
            fixes = self._fixes()
            kept = [c for c in fixes if not (c.source == source_id and c.id == correction_id)]
            if len(kept) == len(fixes):
                raise NotFoundError("Esta correção não existe mais.")
            _write_json(self._fixes_file, [c.model_dump(mode="json") for c in kept])
        self.summaries.pop(source_id, None)

    # ---------------------------------------------------------- execução

    def evaluate(self, source: PdfSource, recipe: Recipe, path: Path, name: str) -> DocRun:
        # cópia profunda: a correção mexe nos campos, e o resultado guardado no cache não pode mudar
        doc = DocRun(name, path, copy.deepcopy(self.cache.extract(path, recipe)))
        apply_corrections(doc, recipe, self.corrections(source.id))
        return doc

    def run(
        self, source_id: str, report: Callable[[str], None] | None = None
    ) -> tuple[PdfSource, Recipe, list[DocRun]]:
        source = self.get(source_id)
        recipe = self.recipe_of(source)
        if recipe is None or not (recipe.campos or recipe.tabelas):
            raise InvalidInputError(
                f"A extração de '{source.name}' ainda é um rascunho: abra a fonte na vista Dados e marque os campos."
            )
        files = self.files_of(source)
        if not files and source.left_out and self._all_files(source):
            raise InvalidInputError(
                f"Todos os PDFs de '{source.name}' foram tirados da fonte: traga algum de volta."
            )
        if not files:
            raise InvalidInputError(f"Nenhum PDF em {source.path} casa com '{source.pattern}'.")
        docs = []
        for i, path in enumerate(files, start=1):
            if report:
                report(f"{i}/{len(files)} PDFs")
            docs.append(self.evaluate(source, recipe, path, path.name))
        counts = {s: sum(1 for d in docs if d.result["estado"] == s) for s in (APROVADO, REVISAR, FALHOU)}
        self.summaries[source_id] = (counts, datetime.now(UTC))
        return source, recipe, docs

    def read(
        self, source_id: str, output: str, report: Callable[[str], None] | None = None
    ) -> tuple[pl.DataFrame, dict[str, Any]]:
        source, recipe, docs = self.run(source_id, report)
        tables = build_outputs(source, recipe, docs)
        if output not in tables:
            raise NotFoundError(
                f"A saída '{output}' não existe em '{source.name}'. Saídas: {', '.join(outputs_of(recipe))}."
            )
        failed = [d for d in docs if d.result["estado"] == FALHOU]
        if failed and source.policy == "parar" and output != "falhas":
            raise InvalidInputError(stop_message(source, docs))
        extra: dict[str, Any] = {
            "source": source.name,
            "pdf_documents": len(docs),
            "pdf_revision": recipe.revisao,
        }
        review = sum(1 for d in docs if d.result["estado"] == REVISAR)
        warnings = []
        if failed:
            warnings.append(
                f"{len(failed)} de {len(docs)} PDF(s) falharam"
                + (" e ficaram de fora" if source.policy == "aprovados" else "")
                + ": veja a saída 'falhas'."
            )
        if review:
            warnings.append(f"{review} de {len(docs)} PDF(s) para revisar: veja a saída 'falhas'.")
        if warnings:
            extra["warnings"] = warnings
        return tables[output], extra

    def signature(self, source_id: str) -> str:
        """Muda quando a extração, a política, uma correção ou o conteúdo de um PDF muda, entra ou sai."""
        source = self.get(source_id)
        recipe = self.recipe_of(source)
        fixes = hashlib.sha256(
            "|".join(
                sorted(
                    f"{c.documento}:{c.campo}:{c.valor}:{c.assinatura}" for c in self.corrections(source_id)
                )
            ).encode()
        ).hexdigest()[:8]
        try:
            files = self.files_of(source)
        except (NotFoundError, InvalidInputError) as exc:
            return f"pdf#erro:{exc}"
        contents = ",".join(f"{p.name}={self.cache.fingerprint(p)}" for p in files)
        return f"pdf#{recipe.digest() if recipe else 'rascunho'}#{source.options_digest()}#{fixes}#{contents}"


EXPORT_KIND = "extracao-pdf"  # sem marca no arquivo (RF-3783)


def _who() -> str:
    try:
        return getpass.getuser()
    except Exception:  # sem usuário no ambiente (serviço): fica registrado como desconhecido
        return "desconhecido"
