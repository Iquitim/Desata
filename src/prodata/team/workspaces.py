"""Espaços da equipe configurados neste computador (spec 047, RF-4701, RF-4716).

Um espaço é uma pasta compartilhada (rede, OneDrive, SharePoint) com a pasta de controle ``_equipe/``. O
``espaco.json`` registra a marca dona: só a mesma marca entra (RF-4701). A lista de espaços em que a pessoa entrou
fica na pasta de dados (``espacos.json``); sem nenhum espaço, nada disto toca a rede (constituição, princípio VIII).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from prodata.errors import InvalidInputError, NotFoundError

CONTROL = "_equipe"
MANIFEST = "espaco.json"
FORMAT = 1
SPACE_ID = r"^[a-f0-9]{16}$"

State = Literal["ok", "somente_leitura", "pasta_ausente", "outra_marca", "invalido"]


class Manifest(BaseModel):
    formato: int = FORMAT
    id: str = Field(pattern=SPACE_ID)
    nome: str = Field(min_length=1, max_length=80)
    marca: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,30}$")
    marca_nome: str = Field(min_length=1, max_length=80)
    criado_em: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Space(BaseModel):
    id: str = Field(pattern=SPACE_ID)
    nome: str
    caminho: str
    estado: State = "ok"
    motivo: str = ""


def _folder(raw: str) -> Path:
    """Pasta escolhida pela pessoa: caminho absoluto e já existente (constituição, princípio IV)."""
    text = raw.strip().strip('"')
    path = Path(text)
    if not text or not path.is_absolute():
        raise InvalidInputError(
            "Escolha a pasta do espaço com o caminho completo, como \\\\servidor\\equipe ou D:\\OneDrive\\Equipe."
        )
    if not path.is_dir():
        raise InvalidInputError(f"A pasta não existe ou não está acessível: {path}")
    return path.resolve()


def read_manifest(root: Path) -> Manifest:
    try:
        return Manifest.model_validate_json((root / CONTROL / MANIFEST).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NotFoundError(
            f"Não há um espaço da equipe em {root}. Crie um, ou escolha a pasta certa."
        ) from exc
    except (OSError, ValidationError, ValueError) as exc:
        raise InvalidInputError(
            f"O espaço em {root} está com o arquivo de controle ilegível ({exc.__class__.__name__})."
        ) from exc


def writable(root: Path, user: str = "teste") -> bool:
    """A pasta deixa gravar? Tenta criar e apagar um arquivo de teste na pasta de controle (RF-4716)."""
    probe = root / CONTROL / f".escrita-{re.sub(r'[^A-Za-z0-9._-]', '_', user)}.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


class Workspaces:
    def __init__(self, registry: Path, brand_id: str, brand_name: str) -> None:
        self._registry = registry
        self._brand_id = brand_id
        self._brand_name = brand_name
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ lista local

    def _load(self) -> list[dict[str, str]]:
        try:
            data = json.loads(self._registry.read_text(encoding="utf-8"))
        except OSError, ValueError:
            return []
        items = data.get("espacos", []) if isinstance(data, dict) else []
        return [i for i in items if isinstance(i, dict) and re.fullmatch(SPACE_ID, str(i.get("id", "")))]

    def _save(self, items: list[dict[str, str]]) -> None:
        self._registry.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._registry.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"formato": FORMAT, "espacos": items}, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        os.replace(tmp, self._registry)

    def configured(self) -> bool:
        """Algum espaço configurado? Sem nenhum, a tela não mostra nada de equipe (RF-4702)."""
        return bool(self._load())

    def spaces(self) -> list[Space]:
        return [self._state(item) for item in self._load()]

    def _state(self, item: dict[str, str]) -> Space:
        root = Path(item["caminho"])
        space = Space(id=item["id"], nome=item.get("nome", ""), caminho=item["caminho"])
        if not root.is_dir():
            return space.model_copy(
                update={
                    "estado": "pasta_ausente",
                    "motivo": "A pasta do espaço não está acessível agora (rede ou sincronização).",
                }
            )
        try:
            manifest = read_manifest(root)
        except (NotFoundError, InvalidInputError) as exc:
            return space.model_copy(update={"estado": "invalido", "motivo": exc.message})
        if manifest.marca != self._brand_id:
            return space.model_copy(
                update={"estado": "outra_marca", "motivo": f"Este espaço é do {manifest.marca_nome}."}
            )
        if not writable(root):
            return space.model_copy(
                update={
                    "estado": "somente_leitura",
                    "motivo": "A pasta não permite gravar para o seu usuário: o espaço abre só para leitura.",
                }
            )
        return space.model_copy(update={"nome": manifest.nome})

    def get(self, space_id: str) -> Space:
        for item in self._load():
            if item["id"] == space_id:
                return self._state(item)
        raise NotFoundError("Esse espaço não está configurado neste computador.")

    def root(self, space_id: str) -> Path:
        return Path(self.get(space_id).caminho)

    # ------------------------------------------------------------------ criar, entrar, sair

    def create(self, raw_path: str, nome: str) -> Space:
        nome = " ".join(nome.split())
        if not nome or len(nome) > 80:
            raise InvalidInputError("Dê um nome ao espaço, de até 80 caracteres.")
        root = _folder(raw_path)
        if (root / CONTROL / MANIFEST).exists():
            raise InvalidInputError("Esta pasta já é um espaço da equipe: use Entrar num espaço.")
        manifest = Manifest(
            id=secrets.token_hex(8), nome=nome, marca=self._brand_id, marca_nome=self._brand_name
        )
        try:
            (root / CONTROL).mkdir(exist_ok=True)
            target = root / CONTROL / MANIFEST
            tmp = target.with_suffix(".tmp")
            tmp.write_text(manifest.model_dump_json(indent=1), encoding="utf-8")
            os.replace(tmp, target)
        except OSError as exc:
            raise InvalidInputError(
                f"Não foi possível criar o espaço nesta pasta: sem permissão de gravar ({exc.strerror})."
            ) from exc
        return self._register(manifest, root)

    def join(self, raw_path: str) -> Space:
        root = _folder(raw_path)
        manifest = read_manifest(root)
        if manifest.marca != self._brand_id:
            raise InvalidInputError(
                f"Este espaço é do {manifest.marca_nome}: abra-o no {manifest.marca_nome}."
            )
        return self._register(manifest, root)

    def _register(self, manifest: Manifest, root: Path) -> Space:
        with self._lock:
            items = [i for i in self._load() if i["id"] != manifest.id]
            items.append({"id": manifest.id, "nome": manifest.nome, "caminho": str(root)})
            self._save(items)
        return self.get(manifest.id)

    def leave(self, space_id: str) -> None:
        """Sai do espaço neste computador. Nada é apagado da pasta compartilhada."""
        with self._lock:
            items = self._load()
            if not any(i["id"] == space_id for i in items):
                raise NotFoundError("Esse espaço não está configurado neste computador.")
            self._save([i for i in items if i["id"] != space_id])
