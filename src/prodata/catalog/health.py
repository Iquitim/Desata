"""Situação dos órgãos (spec 049, RF-4921..4924): No ar, Lenta, Fora do ar desde HH:MM, e o porquê.

- Uma sonda por serviço (a menor consulta possível, de ``hosts.SERVICES``), todas em paralelo, com tempo de 5 s;
  "Lenta" acima de 2 s.
- **Sem internet não é órgão fora do ar** (RF-4923): se todas as sondas falham por falta de conexão (e não por
  resposta do órgão), ninguém é acusado: a situação fica "não conferido" e a tela mostra "Sem conexão".
- "Fora do ar desde" é a hora da primeira falha da sequência atual, vista por este computador.
- Histórico: por serviço e por dia, o pior resultado do dia, nos últimos 30 dias (o que este computador viu, não um
  dado oficial do órgão).
- No máximo uma conferência a cada 5 minutos por serviço, salvo Conferir de novo.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from prodata.catalog import hosts
from prodata.catalog.http import CatalogClient, CatalogError

Situation = Literal["no_ar", "lenta", "fora", "nao_conferido"]
TIMEOUT = 5.0
SLOW = 2.0
THROTTLE = timedelta(minutes=5)
HISTORY_DAYS = 30
_WORSE = {"no_ar": 0, "lenta": 1, "fora": 2}
_PROPFIND = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'


def probe(client: CatalogClient, service: hosts.Service) -> tuple[Situation, float, str, str]:
    """Uma conferência: (situação, segundos, motivo em palavras, tipo da falha)."""
    start = time.perf_counter()
    try:
        if service.id == "receita":
            client.propfind(service.probe, _PROPFIND, auth=(hosts.CNPJ_LINKS[0][0], ""), timeout=TIMEOUT, retries=0,
                            max_bytes=2 * 1024 * 1024)  # fmt: skip
        else:
            method = "HEAD" if service.probe_method == "HEAD" else "GET"
            client.request(method, service.probe, timeout=TIMEOUT, retries=0, max_bytes=2 * 1024 * 1024)  # type: ignore[arg-type]
    except CatalogError as exc:
        return "fora", time.perf_counter() - start, exc.message, exc.kind
    took = time.perf_counter() - start
    if took > SLOW:
        return (
            "lenta",
            took,
            f"{service.site or 'o site do ' + service.short} levou {took:.1f} segundos para responder.",
            "",
        )
    return "no_ar", took, "", ""


class HealthStore:
    """A última conferência de cada serviço e o histórico de 30 dias, em ``<catálogo>/situacao.json``."""

    def __init__(self, root: Path) -> None:
        self.path = root / "situacao.json"
        self._lock = threading.Lock()

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            return {"servicos": {}, "sem_conexao": False, "conferido_em": None}
        return (
            data if isinstance(data, dict) and "servicos" in data else {"servicos": {}, "sem_conexao": False}
        )

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def check(
        self,
        client_factory: Callable[[], CatalogClient],
        services: Iterable[str] | None = None,
        *,
        force: bool = False,
        now: Callable[[], datetime] = datetime.now,
    ) -> dict[str, Any]:
        """Confere os serviços (em paralelo) e grava o resultado. Devolve o estado completo para a tela."""
        wanted = [s for s in (services or hosts.SERVICES) if s in hosts.SERVICES]
        with self._lock:
            data = self.load()
        moment = now()
        if not force:
            fresh = []
            for sid in wanted:
                last = data["servicos"].get(sid, {}).get("conferido_em")
                if not last or moment - datetime.fromisoformat(last) >= THROTTLE:
                    fresh.append(sid)
            wanted = fresh
        if not wanted:
            return data

        def run(sid: str) -> tuple[str, tuple[Situation, float, str, str]]:
            with client_factory() as client:
                return sid, probe(client, hosts.SERVICES[sid])

        with ThreadPoolExecutor(max_workers=min(12, len(wanted))) as pool:
            results = dict(pool.map(run, wanted))

        with self._lock:
            data = self.load()
            offline = len(results) > 1 and all(r[0] == "fora" and r[3] == "conexao" for r in results.values())
            data["sem_conexao"] = offline
            data["conferido_em"] = moment.isoformat()
            today = moment.date().isoformat()
            cutoff = (moment.date() - timedelta(days=HISTORY_DAYS - 1)).isoformat()
            for sid, (situation, took, reason, _kind) in results.items():
                row = data["servicos"].setdefault(sid, {"historico": {}})
                if offline:  # sem internet: ninguém é acusado (RF-4923)
                    row.update(situacao="nao_conferido", motivo="Sem conexão com a internet agora.", segundos=None,
                               conferido_em=moment.isoformat())  # fmt: skip
                    continue
                was_down = row.get("situacao") == "fora"
                row.update(
                    situacao=situation,
                    motivo=reason,
                    segundos=round(took, 2),
                    conferido_em=moment.isoformat(),
                )
                row["desde"] = (
                    (row.get("desde") if was_down else moment.isoformat()) if situation == "fora" else None
                )
                history = {d: s for d, s in row.get("historico", {}).items() if d >= cutoff}
                previous = history.get(today)
                history[today] = (
                    situation if previous is None or _WORSE[situation] > _WORSE[previous] else previous
                )
                row["historico"] = history  # o pior do dia, nos últimos 30 dias
            self._save(data)
        return data


def summary(data: dict[str, Any], service_id: str) -> dict[str, Any]:
    """A situação de um serviço para a tela (sem conferência ainda: "nao_conferido")."""
    row = data.get("servicos", {}).get(service_id) or {}
    return {
        "servico": service_id,
        "situacao": row.get("situacao", "nao_conferido"),
        "motivo": row.get("motivo", ""),
        "segundos": row.get("segundos"),
        "conferido_em": row.get("conferido_em"),
        "desde": row.get("desde"),
        "historico": row.get("historico", {}),
    }
