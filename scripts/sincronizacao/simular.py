"""Duas pessoas, dois computadores e uma pasta sincronizada de verdade (spec 047, T20; CA-02, CA-08).

Sobe dois Syncthing (docker-compose.yml) e dois servidores do programa — Ana e Bruno, cada um com a sua pasta de
dados e a sua cópia da pasta do espaço — e confere, pela API:

1. Ana cria o espaço e salva um fluxo; a pasta chega ao computador do Bruno;
2. Bruno pede para entrar, Ana aceita como Editor e a lista assinada chega ao Bruno;
3. com a sincronização do Bruno pausada (atraso), os dois salvam o mesmo fluxo; ao voltar, a sincronização cria a
   cópia de conflito, e o programa a transforma em versão: nenhum dos dois perde o que salvou.

Uso (com o Docker Desktop aberto)::

    uv run python scripts/sincronizacao/simular.py            # sobe, confere e derruba
    uv run python scripts/sincronizacao/simular.py --manter   # deixa os Syncthing de pé (http://127.0.0.1:8384)

Sai com 1 se alguma conferência falhar.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PASTAS = HERE / "pastas"
SYNC = {"ana": ("http://127.0.0.1:8384", "teste-ana"), "bruno": ("http://127.0.0.1:8385", "teste-bruno")}
APP = {"ana": 8796, "bruno": 8797}
FLOW = {"id": "fechamento", "name": "Fechamento", "edges": [],
        "nodes": [{"id": "n1", "type": "prep.select", "x": 200, "y": 160, "config": {}}]}  # fmt: skip
failed = 0


def check(label: str, ok: bool, detail: object = "") -> None:
    global failed
    failed += not ok
    print(f"{'OK   ' if ok else 'FALHA'} {label}{'' if ok else f'  {detail}'}", flush=True)


def http(method: str, url: str, body: Any = None, headers: dict[str, str] | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,  # noqa: S310 (só 127.0.0.1)
                                 headers={"Content-Type": "application/json", **(headers or {})})  # fmt: skip
    with urllib.request.urlopen(req, timeout=30) as res:  # noqa: S310
        raw = res.read()
    return json.loads(raw) if raw else None


def sync_api(who: str, method: str, path: str, body: Any = None) -> Any:
    base, key = SYNC[who]
    return http(method, f"{base}{path}", body, {"X-API-Key": key})


def app(who: str, method: str, path: str, body: Any = None) -> Any:
    return http(method, f"http://127.0.0.1:{APP[who]}{path}", body)


def wait(label: str, condition: Any, timeout: float = 90) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if condition():
                return True
        except OSError, ValueError, urllib.error.URLError:
            pass
        time.sleep(1)
    check(label, False, f"não aconteceu em {timeout:.0f} s")
    return False


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=HERE, check=True)  # noqa: S603, S607


def pair() -> None:
    """Pareia os dois Syncthing e compartilha a pasta "espaco" (varredura a cada 5 s, com observador de arquivos)."""
    ids = {who: sync_api(who, "GET", "/rest/system/status")["myID"] for who in SYNC}
    for who, other in (("ana", "bruno"), ("bruno", "ana")):
        host = "syncthing-bruno" if other == "bruno" else "syncthing-ana"
        sync_api(who, "PUT", f"/rest/config/devices/{ids[other]}",
                 {"deviceID": ids[other], "name": other, "addresses": [f"tcp://{host}:22000"]})  # fmt: skip
        sync_api(who, "PUT", "/rest/config/folders/espaco", {
            "id": "espaco", "label": "Espaço da equipe", "path": "/var/syncthing/espaco",
            "devices": [{"deviceID": ids["ana"]}, {"deviceID": ids["bruno"]}],
            "rescanIntervalS": 5, "fsWatcherEnabled": True, "fsWatcherDelayS": 1,
        })  # fmt: skip


def start_app(who: str, data: Path) -> subprocess.Popen[bytes]:
    env = {**os.environ, "PRODATA_USUARIO": who, "PRODATA_PORT": str(APP[who]), "PRODATA_STORAGE_DIR": str(data),
           "PRODATA_SECRETS_BACKEND": "memory"}  # fmt: skip
    server = subprocess.Popen([shutil.which("uv") or "uv", "run", "prodata"], cwd=ROOT, env=env,  # noqa: S603
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{APP[who]}/api/health")
            return server
        except OSError:
            time.sleep(1)
    raise SystemExit(f"O servidor de {who} não subiu em 2 minutos.")


def stop_app(server: subprocess.Popen[bytes]) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(server.pid)], capture_output=True, check=False)  # noqa: S603, S607
    else:
        server.terminate()


def scenario() -> None:
    ana_dir, bruno_dir = PASTAS / "ana", PASTAS / "bruno"
    app("ana", "POST", "/api/equipe/identidade", {"nome": "Ana Souza"})
    app("bruno", "POST", "/api/equipe/identidade", {"nome": "Bruno Lima"})
    sid = app(
        "ana",
        "POST",
        "/api/equipe/espacos",
        {"acao": "criar", "caminho": str(ana_dir), "nome": "Controladoria"},
    )["id"]
    app("ana", "PUT", f"/api/equipe/espacos/{sid}/fluxos/fechamento", FLOW)
    if not wait(
        "a pasta do espaço chega ao Bruno", lambda: (bruno_dir / "fechamento.prodata.json").is_file()
    ):
        return
    check("a pasta do espaço chega ao Bruno", True)

    joined = app("bruno", "POST", "/api/equipe/espacos", {"acao": "entrar", "caminho": str(bruno_dir)})
    check("Bruno entra como pedido", joined["papel"] is None and joined["pedido"], joined)
    if not wait(
        "o pedido chega à Ana", lambda: app("ana", "GET", f"/api/equipe/espacos/{sid}/membros")["pedidos"]
    ):
        return
    app(
        "ana",
        "POST",
        f"/api/equipe/espacos/{sid}/membros",
        {"acao": "aceitar", "usuario": "bruno", "papel": "editor"},
    )
    role = lambda: next(s for s in app("bruno", "GET", "/api/equipe")["espacos"] if s["id"] == sid)["papel"]  # noqa: E731
    if not wait("a lista assinada chega ao Bruno", lambda: role() == "editor"):
        return
    check("Bruno vira Editor pela lista assinada que chegou", True)

    base = {
        who: app(who, "GET", f"/api/equipe/espacos/{sid}/fluxos/fechamento/abrir")["sha256"] for who in APP
    }
    sync_api("bruno", "POST", "/rest/system/pause")  # o computador do Bruno fica sem sincronizar (atraso)
    app(
        "ana",
        "PUT",
        f"/api/equipe/espacos/{sid}/fluxos/fechamento?base={base['ana']}",
        {**FLOW, "name": "da Ana"},
    )
    time.sleep(8)  # a versão da Ana chega primeiro à nuvem (ao outro Syncthing)
    app(
        "bruno",
        "PUT",
        f"/api/equipe/espacos/{sid}/fluxos/fechamento?base={base['bruno']}",
        {**FLOW, "name": "do Bruno"},
    )
    sync_api("bruno", "POST", "/rest/system/resume")
    copies = lambda: [p for d in (ana_dir, bruno_dir) for p in d.glob("*sync-conflict*")]  # noqa: E731
    wait("a sincronização cria a cópia de conflito", lambda: bool(copies()), timeout=120)
    time.sleep(10)  # a cópia chega aos dois lados

    names: set[str] = set()
    for who in APP:
        listed = [f["id"] for f in app(who, "GET", f"/api/equipe/espacos/{sid}/fluxos")]
        check(f"{who}: a cópia de conflito não vira fluxo solto", listed == ["fechamento"], listed)
        history = app(
            who, "POST", f"/api/equipe/espacos/{sid}/fluxos/fechamento/versoes/comparar", {"current": None}
        )
        names |= {v["name"] for v in history}
    check("nenhum dos dois perde a versão (as duas estão em Versões)", {"da Ana", "do Bruno"} <= names, names)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        getattr(stream, "reconfigure", lambda **_: None)(encoding="utf-8", errors="replace")
    keep = "--manter" in sys.argv
    shutil.rmtree(PASTAS, ignore_errors=True)
    for who in ("ana", "bruno", "samba"):
        (PASTAS / who).mkdir(parents=True)
    compose("up", "-d", "syncthing-ana", "syncthing-bruno")
    servers: list[subprocess.Popen[bytes]] = []
    try:
        wait(
            "os Syncthing respondem",
            lambda: all(sync_api(w, "GET", "/rest/system/ping") for w in SYNC),
            timeout=120,
        )
        pair()
        with tempfile.TemporaryDirectory(prefix="simular-equipe-", ignore_cleanup_errors=True) as data:
            servers = [start_app(who, Path(data) / who) for who in APP]
            try:
                scenario()
            finally:
                for server in servers:
                    stop_app(server)
                servers = []
    finally:
        for server in servers:
            stop_app(server)
        if not keep:
            compose("down", "-v")
    print("Tudo certo." if not failed else f"{failed} conferência(s) falharam.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
