"""Simulador de sincronização de pasta, no comportamento do OneDrive e do SharePoint (spec 047, T01).

Cada "computador" tem a sua pasta local; a "nuvem" é uma terceira pasta. Nada sincroniza sozinho: o teste chama
``sync(computador)`` quando quer, e é assim que o atraso vira algo explícito e repetível (o colega só vê o arquivo
depois que os dois sincronizarem). Regras imitadas do cliente do OneDrive:

- arquivo mudado só de um lado sobe para a nuvem e desce para os outros;
- arquivo mudado dos dois lados antes de sincronizar vira **conflito**: a nuvem fica com a versão que chegou primeiro
  e a cópia local é renomeada com o nome do computador (``fluxo-NOTEANA.prodata.json``) e também sobe;
- arquivo apagado de um lado some dos outros, se ninguém o mudou nesse meio tempo.

Para "a sincronização segurou o arquivo", os testes usam ``held()``, que mantém o arquivo aberto (no Windows isso
impede trocar o arquivo, como o OneDrive faz enquanto envia).
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(root: Path) -> dict[str, str]:
    """Caminho relativo (com /) -> sha256, ignorando temporários de gravação."""
    out: dict[str, str] = {}
    for p in root.rglob("*"):
        if p.is_file() and not p.name.endswith(".tmp"):
            out[p.relative_to(root).as_posix()] = _digest(p)
    return out


def conflict_name(rel: str, machine: str) -> str:
    """``pasta/fluxo.prodata.json`` -> ``pasta/fluxo-NOTEANA.prodata.json`` (o OneDrive põe o nome antes das extensões)."""
    parent, _, name = rel.rpartition("/")
    stem, dot, ext = name.partition(".")
    renamed = f"{stem}-{machine}{dot}{ext}"
    return f"{parent}/{renamed}" if parent else renamed


class SyncSim:
    def __init__(self, root: Path, machines: tuple[str, ...] = ("NOTEANA", "NOTEBRUNO")) -> None:
        self.cloud = root / "nuvem"
        self.cloud.mkdir(parents=True, exist_ok=True)
        self.local: dict[str, Path] = {}
        self._base: dict[
            str, dict[str, str]
        ] = {}  # o que cada computador viu da nuvem na última sincronização
        for m in machines:
            self.local[m] = root / m
            self.local[m].mkdir(parents=True, exist_ok=True)
            self._base[m] = {}
        self.conflicts: list[str] = []

    def path(self, machine: str) -> Path:
        return self.local[machine]

    def sync(self, machine: str) -> None:
        """Uma rodada de sincronização deste computador: sobe o que mudou aqui, desce o que mudou na nuvem."""
        here, base = self.local[machine], self._base[machine]
        local, cloud = _files(here), _files(self.cloud)
        for rel in sorted(set(local) | set(cloud) | set(base)):
            mine, theirs, seen = local.get(rel), cloud.get(rel), base.get(rel)
            changed_here = mine != seen
            changed_there = theirs != seen
            if changed_here and changed_there and mine != theirs:
                self._conflict(machine, rel, mine, theirs)
            elif changed_here:
                self._upload(here, rel, mine)
            elif changed_there:
                self._download(here, rel, theirs)
        self._base[machine] = _files(self.cloud)

    def sync_all(self, rounds: int = 2) -> None:
        for _ in range(rounds):
            for m in self.local:
                self.sync(m)

    def _upload(self, here: Path, rel: str, digest: str | None) -> None:
        target = self.cloud / rel
        if digest is None:
            target.unlink(missing_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(here / rel, target)

    def _download(self, here: Path, rel: str, digest: str | None) -> None:
        target = here / rel
        if digest is None:
            target.unlink(missing_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.cloud / rel, target)

    def _conflict(self, machine: str, rel: str, mine: str | None, theirs: str | None) -> None:
        here = self.local[machine]
        if mine is None:  # apaguei aqui, mas mudaram lá: a mudança de lá vence e o arquivo volta
            self._download(here, rel, theirs)
            return
        if theirs is None:  # apagaram lá, mas mudei aqui: a minha mudança volta para a nuvem
            self._upload(here, rel, mine)
            return
        renamed = conflict_name(rel, machine)
        (here / rel).rename(here / renamed)
        self._upload(here, renamed, mine)
        self._download(here, rel, theirs)
        self.conflicts.append(renamed)

    @contextmanager
    def held(self, machine: str, rel: str) -> Iterator[None]:
        """Segura o arquivo aberto, como a sincronização enquanto envia."""
        with (self.local[machine] / rel).open("rb"):
            yield
