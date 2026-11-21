"""Identidade de quem usa o programa num espaço da equipe (spec 047, RF-4704).

A identidade é o usuário do Windows, um nome de exibição e uma chave Ed25519 gerada no próprio computador. A chave
privada fica só no cofre do sistema operacional, no serviço da marca ativa: Desata e PRO.DATA têm identidades
separadas, mesmo no mesmo computador (constituição, princípio VIII). O nome de exibição não é segredo e fica na pasta
de dados.
"""

from __future__ import annotations

import base64
import getpass
import json
import os
import re
import threading
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, Field

from prodata.connectors.secrets import SecretStore
from prodata.errors import InvalidInputError

IDENTITY_KEY = "equipe:identidade"
USER_ENV = "PRODATA_USUARIO"  # só para testes: duas "pessoas" no mesmo computador
USER_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"
_INVALID = re.compile(r"[^A-Za-z0-9._-]")


class Identity(BaseModel):
    usuario: str = Field(pattern=USER_PATTERN)
    nome: str = Field(min_length=1, max_length=80)
    chave_publica: str = Field(min_length=40, max_length=60)  # 32 bytes em base64


def windows_user() -> str:
    """O usuário do Windows, só com letras, dígitos e ``._-`` (vira nome de arquivo nas marcas de edição)."""
    raw = os.environ.get(USER_ENV) or getpass.getuser() or "usuario"
    return _INVALID.sub("_", raw)[:64] or "usuario"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def verify(public_key: str, data: bytes, signature: str) -> bool:
    """A assinatura confere com a chave pública? Qualquer dado malformado conta como não conferir."""
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True))
        key.verify(base64.b64decode(signature, validate=True), data)
    except InvalidSignature, ValueError, TypeError:
        return False
    return True


class IdentityStore:
    """A identidade deste computador nesta marca. A chave nasce no primeiro uso."""

    def __init__(self, secrets: SecretStore, path: Path) -> None:
        self._secrets = secrets
        self._path = path  # nome de exibição: {"nome": "..."}
        self._lock = threading.Lock()

    def _private(self) -> Ed25519PrivateKey:
        saved = self._secrets.get(IDENTITY_KEY)
        if saved:
            return Ed25519PrivateKey.from_private_bytes(base64.b64decode(saved))
        key = Ed25519PrivateKey.generate()
        self._secrets.set(IDENTITY_KEY, _b64(key.private_bytes_raw()))
        return key

    def has_name(self) -> bool:
        return self._read().get("nome") is not None

    def _read(self) -> dict[str, str]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def set_name(self, nome: str) -> Identity:
        nome = " ".join(nome.split())
        if not nome or len(nome) > 80:
            raise InvalidInputError("Escreva um nome de exibição de até 80 caracteres.")
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"nome": nome}, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._path)
        return self.current()

    def current(self) -> Identity:
        with self._lock:
            public = self._private().public_key().public_bytes_raw()
        usuario = windows_user()
        return Identity(usuario=usuario, nome=self._read().get("nome") or usuario, chave_publica=_b64(public))

    def sign(self, data: bytes) -> str:
        with self._lock:
            return _b64(self._private().sign(data))
