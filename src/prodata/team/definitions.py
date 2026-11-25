"""Definições da equipe: constantes, conexões, consultas e APIs guardadas no espaço (spec 048, RF-4801..4807).

Na pasta: ``_equipe/definicoes/<tipo>/<id>.json`` e, ao lado, a assinatura de quem salvou (``.sig``). O JSON é o mesmo
modelo de hoje, **sem segredo**: a conexão não tem campo de senha, e a API vai com os parâmetros sigilosos vazios (o
segredo de cada pessoa fica no cofre do próprio computador). Uma definição sem assinatura válida de um Editor aparece
como "não confere" e não é usada por nenhum fluxo.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from prodata.catalog.holidays import TeamHolidayEdits
from prodata.connectors.api_model import SavedApi
from prodata.connectors.models import Connection
from prodata.connectors.queries import SavedQuery
from prodata.domain.constants import NAME_PATTERN, Constant
from prodata.domain.workflow import ID_PATTERN
from prodata.errors import InvalidInputError, NotFoundError
from prodata.team.identity import IdentityStore
from prodata.team.repository import SIG, HeldFileError, atomic_write
from prodata.team.signing import Members, Signature, check_document, sign_document
from prodata.team.workspaces import CONTROL

DefKind = Literal["constantes", "conexoes", "consultas", "apis", "feriados"]
KINDS: dict[str, type[BaseModel]] = {
    "constantes": Constant,
    "conexoes": Connection,
    "consultas": SavedQuery,
    "apis": SavedApi,
    # Edições dos feriados (spec 049, RF-4948): datas, nomes e leis, sem segredo.
    "feriados": TeamHolidayEdits,
}
KIND_NAMES = {"constantes": "constante", "conexoes": "conexão", "consultas": "consulta", "apis": "API",
              "feriados": "lista de feriados"}  # fmt: skip
DEFINITIONS_DIR = "definicoes"
_KEY = {"constantes": re.compile(NAME_PATTERN)}
_ID = re.compile(ID_PATTERN)

AnyDefinition = Constant | Connection | SavedQuery | SavedApi | TeamHolidayEdits


def key_of(kind: str, item: BaseModel) -> str:
    """O identificador da definição: o nome, para a constante; o id, para as outras."""
    return str(getattr(item, "name" if kind == "constantes" else "id"))


def without_secrets(kind: str, item: BaseModel) -> BaseModel:
    """O que pode ir para a pasta (constituição, princípio IV): parâmetros sigilosos da API vão vazios. A conexão
    não tem campo de senha; a senha e os segredos de autenticação ficam sempre no cofre de cada computador."""
    if kind == "apis" and isinstance(item, SavedApi):
        return item.model_copy(update={
            "params": [p.model_copy(update={"value": ""}) if p.secret else p for p in item.params],
            "headers": [p.model_copy(update={"value": ""}) if p.secret else p for p in item.headers],
        })  # fmt: skip
    return item


def content_of(kind: str, item: BaseModel) -> dict[str, Any]:
    data: dict[str, Any] = without_secrets(kind, item).model_dump(mode="json")
    return data


class DefinitionInfo(BaseModel):
    tipo: DefKind
    id: str
    nome: str
    autor: str = ""
    autor_nome: str = ""
    quando: datetime | None = None
    confere: bool = False
    motivo: str | None = None


class TeamDefinitions:
    def __init__(self, space_root: Path, space_id: str) -> None:
        self.folder = space_root / CONTROL / DEFINITIONS_DIR
        self.space_id = space_id

    def _path(self, kind: str, key: str) -> Path:
        if kind not in KINDS:
            raise InvalidInputError("Tipo de definição desconhecido.")
        if not (_KEY.get(kind) or _ID).match(key):
            raise InvalidInputError("Identificador inválido.")
        return self.folder / kind / f"{key}.json"

    def save(self, kind: str, item: BaseModel, identity: IdentityStore) -> None:
        model = KINDS.get(kind)
        if model is None or not isinstance(item, model):
            raise InvalidInputError("Tipo de definição desconhecido.")
        key = key_of(kind, item)
        path = self._path(kind, key)
        data = content_of(kind, item)
        signature = sign_document(identity, self.space_id, f"{kind}/{key}", data)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            atomic_write(path, json.dumps(data, ensure_ascii=False, indent=1))
            atomic_write(path.with_name(f"{path.name}{SIG}"), signature.model_dump_json(indent=1))
        except PermissionError as exc:
            raise HeldFileError(
                "A pasta do espaço segurou o arquivo: tente de novo em instantes. Nada foi perdido."
            ) from exc

    def delete(self, kind: str, key: str) -> None:
        path = self._path(kind, key)
        if not path.is_file():
            raise NotFoundError(f"Essa {KIND_NAMES.get(kind, 'definição')} não está mais no espaço.")
        path.unlink()
        path.with_name(f"{path.name}{SIG}").unlink(missing_ok=True)

    def _read(self, kind: str, key: str) -> tuple[dict[str, Any] | None, Signature | None]:
        path = self._path(kind, key)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            return None, None
        try:
            signature = Signature.model_validate_json(
                path.with_name(f"{path.name}{SIG}").read_text(encoding="utf-8")
            )
        except OSError, ValidationError, ValueError:
            signature = None
        return (data if isinstance(data, dict) else None), signature

    def check(self, kind: str, key: str, members: Members | None) -> tuple[AnyDefinition | None, str | None]:
        """A definição, se confere; senão, None e o motivo."""
        data, signature = self._read(kind, key)
        if data is None:
            return None, "Não está no espaço."
        reason = check_document(signature, self.space_id, f"{kind}/{key}", data, members)
        if reason:
            return None, reason
        try:
            item = KINDS[kind].model_validate(data)
        except ValidationError:
            return None, "O arquivo da definição está ilegível."
        if key_of(kind, item) != key:
            return None, "O arquivo da definição não corresponde ao nome dele."
        return item, None  # type: ignore[return-value]

    def get(self, kind: str, key: str, members: Members | None) -> AnyDefinition | None:
        return self.check(kind, key, members)[0]

    def keys(self, kind: str) -> list[str]:
        folder = self.folder / kind
        if kind not in KINDS or not folder.is_dir():
            return []
        pattern = _KEY.get(kind) or _ID
        return sorted(p.stem for p in folder.glob("*.json") if pattern.match(p.stem))

    def list(self, kind: str, members: Members | None) -> list[tuple[DefinitionInfo, AnyDefinition | None]]:
        """Todas as definições do tipo, com a situação (confere ou o motivo) e o modelo quando confere."""
        out: list[tuple[DefinitionInfo, AnyDefinition | None]] = []
        for key in self.keys(kind):
            data, signature = self._read(kind, key)
            item, reason = self.check(kind, key, members)
            name = str((data or {}).get("name") or key)
            info = DefinitionInfo(tipo=kind, id=key, nome=name, confere=item is not None, motivo=reason,
                                  autor=signature.autor if signature else "",
                                  autor_nome=(signature.nome or signature.autor) if signature else "",
                                  quando=signature.quando if signature else None)  # fmt: skip
            out.append((info, item))
        return out
