"""Confere os executáveis gerados pelo build, como alguém que instalou o programa (antes de cada versão).

    uv run python scripts/conferir_exe.py                 # as marcas que estiverem em dist/
    uv run python scripts/conferir_exe.py Desata PRO.DATA

Para cada marca: versão, biblioteca, o fluxo de exemplo inteiro (com a etapa de PDFs e o laço), o código de saída de um
fluxo inexistente e o executável da tarefa agendada gravando o histórico. Usa uma pasta de dados temporária: não mexe
na biblioteca de ninguém. Sai com 1 se alguma conferência falhar.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
VERSION = re.search(
    r'__version__ = "([^"]+)"', (ROOT / "src/prodata/__init__.py").read_text(encoding="utf-8")
)


class Checks:
    def __init__(self) -> None:
        self.failed = 0

    def __call__(self, name: str, ok: bool, detail: object = "") -> None:
        self.failed += not ok
        print(("OK    " if ok else "FALHA ") + name + ("" if ok else f"  {detail}"))


def conferir(brand: str, check: Checks) -> None:
    exe = DIST / brand / "prodata-cli.exe"
    print(f"== {brand}")
    if not exe.is_file():
        check("executável no pacote", False, exe)
        return
    data = Path(tempfile.mkdtemp(prefix="conferir-exe-"))
    env = {
        **os.environ,
        "PRODATA_STORAGE_DIR": str(data),
        "PRODATA_SECRETS_BACKEND": "memory",
        "PYTHONIOENCODING": "utf-8",
    }

    def run(program: Path, *args: str) -> tuple[int, str, str]:
        res = subprocess.run([str(program), *args], env=env, capture_output=True, timeout=400, check=False)  # noqa: S603
        return res.returncode, res.stdout.decode("utf-8", "replace"), res.stderr.decode("utf-8", "replace")

    version = VERSION.group(1) if VERSION else "?"
    code, out, err = run(exe, "--version")
    check(f"versão {version}", code == 0 and version in out and brand in out, (code, out, err[-300:]))
    code, out, err = run(exe, "list")
    check("lista a biblioteca", code == 0 and "Pipeline 360" in out, (code, out[:200], err[-400:]))
    flow_id = out.strip().splitlines()[-1].split("\t")[0] if out.strip() else ""
    code, out, err = run(exe, "run", flow_id, "--relatorio", str(data / "r.json"))
    check(
        "executa o exemplo inteiro e sai com 0",
        code == 0 and "Concluído" in out,
        (code, out[-600:], err[-600:]),
    )
    report = json.loads((data / "r.json").read_text(encoding="utf-8")) if (data / "r.json").is_file() else {}
    results = report.get("node_results", {})
    bad = {k: v.get("status") for k, v in results.items() if v.get("status") not in ("executed", "cached")}
    check("nenhuma caixa com erro", not bad, bad)
    pdf = [k for k in results if k.startswith("n_pdf_")]
    check("etapa de PDFs executada: 11 caixas", len(pdf) == 11, sorted(pdf))
    loop = results.get("n_laco_fim", {})
    check(
        "etapa do laço executada",
        loop.get("status") in ("executed", "cached") and "voltas" in loop.get("annotation", ""),
        loop,
    )
    # o exemplo lê os PDFs da pasta do próprio pacote (não copia para a pasta de dados)
    check("PDFs de exemplo no pacote", len(list((DIST / brand).rglob("arrecadacao_*.pdf"))) >= 3)
    code, out, err = run(exe, "run", "nao_existe")
    check("fluxo inexistente sai com 2", code == 2 and "não encontrado" in err, (code, err[-200:]))
    task = exe.with_name(
        "prodata-tarefa.exe"
    )  # spec 044: a tarefa agendada roda sem console e grava o histórico
    check("prodata-tarefa.exe no pacote", task.is_file())
    if task.is_file():
        code, _out, _err = run(task, "run", flow_id, "--agendamento", "abcdef12")
        history = data / "logs" / "agendamentos.jsonl"
        lines = history.read_text(encoding="utf-8").splitlines() if history.is_file() else []
        last = json.loads(lines[-1]) if lines else {}
        check("tarefa agendada executa e grava o histórico",
              code == 0 and last.get("status") == "ok" and last.get("schedule_id") == "abcdef12", (code, last))  # fmt: skip


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # acentos certos no console do Windows
        getattr(stream, "reconfigure", lambda **_: None)(encoding="utf-8", errors="replace")
    version = VERSION.group(1) if VERSION else ""
    # sem argumentos: as marcas com instalador desta versão (pacotes antigos que sobraram em dist/ ficam de fora)
    brands = sys.argv[1:] or sorted(
        p.parent.name
        for p in DIST.glob("*/prodata-cli.exe")
        if (DIST / f"{p.parent.name}-{version}-setup.exe").is_file()
    )
    if not brands:
        print("Nenhum pacote em dist/: rode o build antes (uv run python packaging/build.py).")
        return 1
    check = Checks()
    for brand in brands:
        conferir(brand, check)
    print(f"{'Tudo certo' if not check.failed else f'{check.failed} falha(s)'} em {', '.join(brands)}.")
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
