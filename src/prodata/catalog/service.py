"""O catálogo de dados públicos para a tela (spec 049): visão geral, busca, atualização e preferências.

Nada aqui acessa a rede ao ser criado (RF-4983): o cliente do catálogo só nasce quando a tela pede Atualizar, uma
busca ao vivo ou a situação dos órgãos, com o catálogo aberto.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from prodata.catalog import curated, portals, sources
from prodata.catalog.http import CatalogClient
from prodata.catalog.index import AGENCY_BY_ID, CatalogStore
from prodata.catalog.model import SourceNotFoundError
from prodata.catalog.readers import bcb_olinda, ckan, files

RECENTS = 20


class Preferences:
    """Favoritos e recentes deste computador (RF-4905): não vão para o fluxo nem para o espaço da equipe."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            return {"favoritos": [], "recentes": []}
        return {"favoritos": list(data.get("favoritos", [])), "recentes": list(data.get("recentes", []))}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self) -> dict[str, Any]:
        with self._lock:
            return self._load()

    def toggle_favorite(self, source_id: str) -> bool:
        with self._lock:
            data = self._load()
            on = source_id not in data["favoritos"]
            data["favoritos"] = (
                [*data["favoritos"], source_id] if on else [f for f in data["favoritos"] if f != source_id]
            )
            self._save(data)
            return on

    def add_recent(self, source_id: str) -> None:
        with self._lock:
            data = self._load()
            data["recentes"] = [source_id, *[r for r in data["recentes"] if r != source_id]][:RECENTS]
            self._save(data)


class CatalogService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.store = CatalogStore(root)
        self.prefs = Preferences(root / "preferencias.json")
        self._job_lock = threading.Lock()
        self._job: dict[str, Any] = {"rodando": False, "orgaos": {}, "inicio": None, "fim": None}

    # ---------------------------------------------------------------- visão geral

    def overview(self) -> dict[str, Any]:
        state = self.store.state()
        prefs = self.prefs.get()
        counts: dict[str, int] = {}
        for source in curated.SOURCES:
            counts[source.categoria] = counts.get(source.categoria, 0) + 1
        counts["series"] = state["ipea"].quantidade
        categories = [
            {"id": c.id, "nome": c.nome, "icone": c.icone, "quantidade": counts.get(c.id, 0)}
            for c in curated.CATEGORIES
        ]
        portal_rows = [
            {
                "id": p.id,
                "nome": p.nome,
                "orgao": p.orgao,
                "esfera": p.esfera,
                "nota": p.nota,
                "pagina": p.pagina,
                **_state_json(state[p.id]),
            }
            for p in portals.PORTALS
        ]
        agencies = {a: _state_json(state[a]) for a in ("bcb", "ibge", "ipea")}
        read = [s.lido_em for s in state.values() if s.lido_em]
        return {
            "categorias": categories,
            "portais": portal_rows,
            "orgaos": agencies,
            "lido_em": min(read).isoformat() if read else None,
            "desatualizado": self.store.stale(),
            "favoritos": len(prefs["favoritos"]),
            "recentes": len(prefs["recentes"]),
            "destaques": len(curated.SOURCES),
            "atualizacao": self.refresh_status(),
        }

    # ---------------------------------------------------------------- busca

    def search(
        self,
        query: str = "",
        *,
        agency: str | None = None,
        category: str | None = None,
        periodicity: str | None = None,
        special: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if special in ("favoritos", "recentes"):
            wanted = self.prefs.get()[special]
            found = {e["id"]: e for e in self.store.search(query, limit=100_000)}
            rows = [found[i] for i in wanted if i in found]
            return rows[:limit]
        if special == "destaques":
            return [
                e for e in self.store.search(query, agency=agency, periodicity=periodicity) if e["destaque"]
            ][:limit]
        return self.store.search(
            query, agency=agency, category=category, periodicity=periodicity, limit=limit
        )

    # ---------------------------------------------------------------- detalhe e prévia (RF-4911..4915)

    def describe(self, source_id: str) -> dict[str, Any]:
        with CatalogClient(timeout=30) as client:
            return sources.describe(client, source_id)

    def preview(self, source_id: str, choices: dict[str, Any]) -> dict[str, Any]:
        with CatalogClient(timeout=90) as client:
            return sources.preview(client, source_id, choices, self.root)

    def file_preview(
        self, source_id: str, resource_id: str, options: dict[str, Any], member: str
    ) -> dict[str, Any]:
        """A prévia obrigatória do arquivo de um portal (RF-4938), com as opções que a pessoa trocou."""
        parts = sources.check_id(source_id)
        if parts[0] != "ckan" or len(parts) != 3:
            raise SourceNotFoundError("Só arquivos de portais têm prévia de arquivo.")
        with CatalogClient(timeout=180) as client:
            detail = ckan.dataset(client, parts[1], parts[2])
            resource = next((a for a in detail["arquivos"] if a["id"] == resource_id), None)
            if resource is None:
                raise SourceNotFoundError("O portal não tem mais este arquivo.")
            if resource["situacao"] != "legivel":
                raise SourceNotFoundError(resource["motivo"] or "Este arquivo não tem prévia.")
            return files.preview(
                client, resource["url"], self.root, resource["formato"], options=options, member=member
            )

    def odata(self, source_id: str, resource_id: str) -> dict[str, Any]:
        parts = sources.check_id(source_id)
        if parts[0] != "ckan" or len(parts) != 3:
            raise SourceNotFoundError("Só conjuntos de portais têm serviço OData.")
        with CatalogClient(timeout=60) as client:
            detail = ckan.dataset(client, parts[1], parts[2])
            resource = next((a for a in detail["arquivos"] if a["id"] == resource_id), None)
            if resource is None or resource["situacao"] != "odata":
                raise SourceNotFoundError("Este arquivo não é um serviço OData do Banco Central.")
            return sources.odata_entries(client, resource["url"])

    def currencies(self) -> list[dict[str, str]]:
        with CatalogClient(timeout=30) as client:
            return bcb_olinda.currencies(client)

    # ---------------------------------------------------------------- atualizar (RF-4933)

    def refresh_status(self) -> dict[str, Any]:
        with self._job_lock:
            return json.loads(json.dumps(self._job, default=str))

    def start_refresh(self, agencies: list[str] | None = None) -> dict[str, Any]:
        """Lê de novo os catálogos dos órgãos em segundo plano. Uma atualização por vez."""
        chosen = [a for a in (agencies or list(AGENCY_BY_ID)) if a in AGENCY_BY_ID]
        with self._job_lock:
            if self._job["rodando"]:
                return json.loads(json.dumps(self._job, default=str))
            self._job = {
                "rodando": True,
                "orgaos": {a: "esperando" for a in chosen},
                "inicio": datetime.now().isoformat(),
                "fim": None,
            }
        threading.Thread(
            target=self._run_refresh, args=(chosen,), name="catalogo-atualizar", daemon=True
        ).start()
        return self.refresh_status()

    def _progress(self, agency: str, state: str) -> None:
        with self._job_lock:
            self._job["orgaos"][agency] = state

    def _run_refresh(self, chosen: list[str]) -> None:
        try:
            with CatalogClient(timeout=120) as client:
                self.store.refresh(client, chosen, progress=self._progress)
        finally:
            with self._job_lock:
                self._job["rodando"] = False
                self._job["fim"] = datetime.now().isoformat()


def _state_json(state: Any) -> dict[str, Any]:
    return {
        "quantidade": state.quantidade,
        "lido_em": state.lido_em.isoformat() if state.lido_em else None,
        "erro": state.erro,
        "erro_em": state.erro_em.isoformat() if state.erro_em else None,
        "aviso": state.aviso,
    }
