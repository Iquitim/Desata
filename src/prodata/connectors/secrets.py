"""Armazenamento de senhas. Em produção: cofre do sistema (Windows Credential Manager,
macOS Keychain, Secret Service). Em testes: memória."""

from __future__ import annotations

import contextlib
import secrets
from typing import Protocol

import keyring
from keyring.errors import PasswordDeleteError

from prodata.brand import marca

# Serviço no cofre do Windows: um por marca, para duas marcas instaladas não se misturarem (spec 036).
SERVICE = marca().vault_service


class SecretStore(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...


INSTALLATION_KEY = "instalacao:mask"


def installation_key(store: SecretStore) -> bytes:
    """Chave deste computador para o código estável do Mask (spec 033). Nasce no primeiro uso e fica no cofre."""
    saved = store.get(INSTALLATION_KEY)
    if not saved:
        saved = secrets.token_hex(32)
        store.set(INSTALLATION_KEY, saved)
    return bytes.fromhex(saved)


class KeyringSecretStore:
    """Cofre do sistema. ``service``: o serviço da marca ativa; outro só para a mudança de marca (spec 036)."""

    def __init__(self, service: str = SERVICE) -> None:
        self.service = service

    def get(self, key: str) -> str | None:
        return keyring.get_password(self.service, key)

    def set(self, key: str, value: str) -> None:
        keyring.set_password(self.service, key, value)

    def delete(self, key: str) -> None:
        # Se já não existia, o estado desejado (sem segredo) foi atingido.
        with contextlib.suppress(PasswordDeleteError):
            keyring.delete_password(self.service, key)


class MemorySecretStore:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)
