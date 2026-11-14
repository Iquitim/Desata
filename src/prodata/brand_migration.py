"""Mudança de marca no mesmo computador (spec 036, RF-3622 e RF-3623).

Na primeira abertura de uma marca, com a pasta de dados dela ainda vazia, oferece trazer os dados de outra marca
(``migrar_de`` no marca.toml). Copia, nunca move: a pasta antiga fica intacta. As senhas vão de um serviço do cofre do
Windows para o outro só com a confirmação da pessoa, neste computador e neste usuário; nada sai da máquina.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from prodata.brand import Brand
from prodata.connectors.api_store import ApiStore
from prodata.connectors.api_store import secret_key as api_secret_key
from prodata.connectors.jira_store import JiraStore
from prodata.connectors.secrets import INSTALLATION_KEY, MemorySecretStore, SecretStore
from prodata.connectors.store import ConnectionStore
from prodata.connectors.store import secret_key as connection_secret_key

MARKER = "marca-migracao.json"
# Fica para trás: o que é desta janela ou deste computador, refeito sozinho, e os arquivos que os fluxos gravaram.
SKIP = ("logs", "webview", "cache", "cache_arrow", "exports")
_EMPTY_OK = {"logs", "webview"}


@dataclass(frozen=True)
class Source:
    folder: Path
    service: str
    name: str


def source_for(brand: Brand, data_dir: Path) -> Source | None:
    """De onde trazer os dados, quando faz sentido oferecer: pasta da marca vazia, sem resposta anterior."""
    if (data_dir / MARKER).exists():
        return None
    if data_dir.is_dir() and any(p.name not in _EMPTY_OK for p in data_dir.iterdir()):
        return None
    for item in brand.instalacao.migrar_de:
        folder = data_dir.parent / item.get("pasta", "")
        if item.get("pasta") and folder != data_dir and folder.is_dir() and any(folder.iterdir()):
            return Source(folder, item.get("cofre", ""), item.get("nome") or item["pasta"])
    return None


def copy_data(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*SKIP), dirs_exist_ok=True)


def secret_keys(storage: Path) -> list[str]:
    """As chaves que as configurações copiadas usam no cofre: conexões, APIs, Jira e a chave do Mask."""
    empty = MemorySecretStore()
    keys = [INSTALLATION_KEY]
    keys += [connection_secret_key(c.id) for c in ConnectionStore(storage / "connections.json", empty).list()]
    for api in ApiStore(storage / "apis.json", empty).list():
        keys += [api_secret_key(api.id, slot) for slot in api.missing_secrets]
    if (storage / "jira").is_dir():
        for conn in JiraStore(storage / "jira", empty).connections():
            keys += [f"jira:{conn.id}:email", f"jira:{conn.id}:token"]
    return keys


def copy_secrets(keys: list[str], source: SecretStore, target: SecretStore) -> tuple[int, list[str]]:
    """Copia o que existe. Devolve quantas foram copiadas e as chaves que não puderam ser lidas."""
    copied, missing = 0, []
    for key in keys:
        try:
            value = source.get(key)
        except Exception:  # cofre recusou a leitura: a pessoa digita de novo
            value = None
        if value is None:
            if key != INSTALLATION_KEY:
                missing.append(key)
            continue
        target.set(key, value)
        copied += 1
    return copied, missing


def remember(data_dir: Path, source: Source, *, data: bool, secrets: bool, missing: list[str]) -> None:
    """Grava a resposta: a oferta não aparece de novo."""
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / MARKER).write_text(
        json.dumps(
            {
                "de": str(source.folder),
                "quando": datetime.now(UTC).isoformat(timespec="seconds"),
                "dados": data,
                "senhas": secrets,
                "senhas_faltando": missing,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
