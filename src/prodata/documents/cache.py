"""Cache das palavras e das extrações (spec 037, RF-3783).

A chave é o **conteúdo** do PDF (resumo BLAKE2 dos bytes), não o nome: trocar o arquivo por outro com o mesmo nome
refaz a leitura; copiar o mesmo arquivo para outro lugar aproveita. Tamanho e data só servem para não recalcular o
resumo a cada pedido. As palavras vão para memória e disco; as extrações, só para memória (a chave inclui o ``digest``
da extração e a versão do motor). PDF aberto com senha nunca vai para o disco.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from prodata.documents.extract import extract, unsupported
from prodata.documents.reader import PdfReadError
from prodata.documents.recipe import ENGINE_VERSION, Recipe
from prodata.documents.worker import PdfWorker

_CHUNK = 2**20
_UNREADABLE = {
    "sem_texto": "página sem texto legível (escaneada?)",
    "protegido": "protegido por senha",
    "malformado": "arquivo danificado ou incompleto",
    "grande_demais": "arquivo grande demais",
    "tempo_esgotado": "a leitura passou do tempo limite",
    "memoria": "a leitura passou do limite de memória",
    "leitor_caiu": "o leitor de PDF parou",
}
_STABLE = {
    "sem_texto",
    "protegido",
    "malformado",
    "grande_demais",
}  # mesmo arquivo, mesma falha: pode guardar


def content_hash(path: Path) -> str:
    digest = hashlib.blake2b(digest_size=16)
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def failure_text(code: str) -> str:
    return _UNREADABLE.get(code, "não foi possível ler o PDF")


class _Lru(OrderedDict[Any, Any]):
    def __init__(self, size: int) -> None:
        super().__init__()
        self.size = size

    def get_fresh(self, key: Any) -> Any:
        if key not in self:
            return None
        self.move_to_end(key)
        return self[key]

    def put(self, key: Any, value: Any) -> None:
        self[key] = value
        self.move_to_end(key)
        while len(self) > self.size:
            self.popitem(last=False)


class DocumentCache:
    def __init__(self, folder: Path, worker: PdfWorker, memory_items: int = 32) -> None:
        self.folder = folder
        self.worker = worker
        self._stats: dict[str, tuple[int, int, str]] = {}
        self._words = _Lru(memory_items)
        self._results = _Lru(memory_items * 8)
        self._lock = threading.Lock()
        self.reads = 0  # quantas vezes o PDF foi lido de fato (os testes conferem o cache por aqui)

    def fingerprint(self, path: Path) -> str:
        stat = path.stat()
        key = str(path.resolve())
        known = self._stats.get(key)
        if known and known[:2] == (stat.st_size, stat.st_mtime_ns):
            return known[2]
        digest = content_hash(path)
        self._stats[key] = (stat.st_size, stat.st_mtime_ns, digest)
        return digest

    def _disk(self, fp: str) -> Path:
        return self.folder / f"{fp}-m{ENGINE_VERSION}.json.gz"

    def words(self, path: Path, password: str | None = None) -> dict[str, Any]:
        """Páginas e palavras do PDF; levanta ``PdfReadError`` (também guardado: um PDF quebrado não é relido)."""
        fp = self.fingerprint(path)
        with self._lock:
            hit = self._words.get_fresh((fp, bool(password)))
            if hit is None and not password and self._disk(fp).exists():
                try:
                    hit = json.loads(gzip.decompress(self._disk(fp).read_bytes()))
                except OSError, ValueError:
                    hit = None
                if hit is not None:
                    self._words.put((fp, False), hit)
        if hit is None:
            self.reads += 1
            try:
                hit = self.worker.call("inspect", path=str(path), password=password)
            except PdfReadError as exc:
                if exc.code not in _STABLE:  # tempo e memória podem dar certo numa próxima vez
                    raise
                hit = {"erro": exc.code, "detalhe": exc.detail}
            with self._lock:
                self._words.put((fp, bool(password)), hit)
                if not password and "erro" not in hit and hit["pages"]:
                    self.folder.mkdir(parents=True, exist_ok=True)
                    tmp = self._disk(fp).with_suffix(".tmp")
                    tmp.write_bytes(gzip.compress(json.dumps(hit, ensure_ascii=False).encode(), 5))
                    tmp.replace(self._disk(fp))
        if "erro" in hit:
            raise PdfReadError(hit["erro"], hit.get("detalhe", ""))
        return hit

    def extract(self, path: Path, recipe: Recipe, password: str | None = None) -> dict[str, Any]:
        """Resultado da extração para um arquivo, com a assinatura do conteúdo (para correções e origem)."""
        fp = self.fingerprint(path)
        key = (fp, recipe.digest(), bool(password))
        with self._lock:
            cached = self._results.get_fresh(key)
        if cached is not None:
            return dict(cached)
        try:
            result = extract(recipe, self.words(path, password)).as_dict()
        except PdfReadError as exc:
            result = unsupported(recipe, failure_text(exc.code)).as_dict()
            result["erro"] = exc.code
        result["assinatura"] = fp
        with self._lock:
            self._results.put(key, result)
        return dict(result)
