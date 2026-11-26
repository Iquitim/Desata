"""Confere os executáveis gerados pelo build, como alguém que instalou o programa (antes de cada versão).

    uv run python scripts/conferir_exe.py                 # as marcas que estiverem em dist/
    uv run python scripts/conferir_exe.py Desata PRO.DATA

Para cada marca: versão, biblioteca, o fluxo de exemplo inteiro (com a etapa de PDFs e o laço), o código de saída de um
fluxo inexistente, a versão oficial de um espaço da equipe (assinatura conferida no executável) e o executável da
tarefa agendada gravando o histórico. Usa uma pasta de dados temporária: não mexe
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


BRAND_IDS = {"Desata": "desata", "PRO.DATA": "protege", "Neutro": "neutra"}


def team_official(data: Path, brand: str) -> str:
    """Spec 047: um espaço com versão oficial assinada, montado pelo código-fonte na pasta de dados do executável.
    O executável confere a assinatura (Ed25519, da biblioteca cryptography) ao rodar ``espaco:<id>/<fluxo>``."""
    from prodata.connectors.secrets import MemorySecretStore
    from prodata.domain.workflow import Workflow
    from prodata.services.workflows import WorkflowRepository
    from prodata.team.identity import IdentityStore
    from prodata.team.service import TeamService
    from prodata.team.workspaces import Workspaces

    folder = data / "espaco_da_equipe"
    folder.mkdir()
    team = TeamService(Workspaces(data / "espacos.json", BRAND_IDS.get(brand, brand.lower()), brand),
                       IdentityStore(MemorySecretStore(), data / "equipe.json"), WorkflowRepository(data / "fonte"),
                       data / "equipe")  # fmt: skip
    space = team.create(str(folder), "Conferência")["id"]
    flow = Workflow.model_validate({"id": "oficial", "name": "Fluxo oficial", "edges": [], "nodes": [
        {"id": "t", "type": "io.text_input", "config": {"table": {"columns": ["a"], "rows": [["1"]]}}}]})  # fmt: skip
    team.save(space, flow)
    team.publish(space, "oficial")
    return space


def public_flows(data: Path) -> None:
    """Spec 049: dois fluxos com a caixa Dados públicos, para o executável rodar sem rede.

    - Selic diária, com uma leitura guardada na pasta de dados (como depois de uma execução com internet): sem
      rede, a caixa usa essa leitura e avisa; com Exigir dados atuais, falha com o motivo.
    - Feriados de São Paulo: calculados pelo próprio programa (as tabelas vão no pacote), sem rede nenhuma.
    """
    from datetime import date, datetime

    import polars as pl

    from prodata.catalog import cache
    from prodata.domain.workflow import Workflow
    from prodata.services.trust import TrustRegistry

    choices = {"periodo": {"kind": "ultimos_anos", "anos": 1}}
    frame = pl.DataFrame({"data": [date(2026, 11, 24), date(2026, 11, 25)], "valor": [0.050788, 0.050788]})
    cache.save(data / "catalogo", "bcb.sgs/11", choices, frame, datetime(2026, 11, 25, 9, 30))
    selic = {"id": "bcb.sgs/11", "nome": "Taxa Selic diária", "orgao": "Banco Central do Brasil",
             "citacao": "Banco Central do Brasil, SGS 11", "escolhas": choices}  # fmt: skip
    year = date.today().year
    holidays = {"id": "calendario/feriados", "nome": "Feriados", "escolhas": {
        "local": "SP", "periodo": {"kind": "intervalo", "inicio": f"{year}-07-09", "fim": f"{year}-07-09"}}}  # fmt: skip
    folder = data / "workflows"
    folder.mkdir(parents=True, exist_ok=True)
    flows = {
        "selic_guardada": {"fonte": selic},
        "selic_atual": {"fonte": selic, "exigir_atual": True},
        "feriados_sp": {"fonte": holidays},
    }
    for flow_id, config in flows.items():
        body = {"id": flow_id, "name": flow_id, "edges": [],
                "nodes": [{"id": "p", "type": "io.public_data", "label": "Dados públicos", "config": config}]}  # fmt: skip
        (folder / f"{flow_id}.prodata.json").write_text(
            json.dumps(body, ensure_ascii=False), encoding="utf-8"
        )
        # Feito "neste computador" (como o exemplo): a proteção da spec 046 recusa fluxo de fora não conferido.
        TrustRegistry(data / "confianca.json").created(Workflow.model_validate(body))


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
    space = team_official(data, brand)
    code, out, err = run(exe, "run", f"espaco:{space}/oficial")
    check(
        "espaço da equipe: roda a versão oficial assinada",
        code == 0 and "Concluído" in out,
        (code, out[-300:], err[-400:]),
    )
    official = next((data / "espaco_da_equipe" / "_equipe" / "oficiais").glob("oficial.prodata.json"))
    official.write_text(
        official.read_text(encoding="utf-8").replace("Fluxo oficial", "Adulterado"), encoding="utf-8"
    )
    code, out, err = run(exe, "run", f"espaco:{space}/oficial")
    check(
        "espaço da equipe: oficial adulterada não roda",
        code == 2 and "não confere" in err,
        (code, err[-300:]),
    )
    # Dados públicos (spec 049, T20): sem rede, a leitura guardada; os feriados, calculados pelo programa
    public_flows(data)
    offline = {**env, "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}

    def run_offline(*args: str) -> tuple[int, str, str]:
        res = subprocess.run([str(exe), *args], env=offline, capture_output=True, timeout=400, check=False)  # noqa: S603
        return res.returncode, res.stdout.decode("utf-8", "replace"), res.stderr.decode("utf-8", "replace")

    code, out, err = run_offline("run", "selic_guardada", "--relatorio", str(data / "selic.json"))
    selic = (
        json.loads((data / "selic.json").read_text(encoding="utf-8"))
        if (data / "selic.json").is_file()
        else {}
    )
    node = selic.get("node_results", {}).get("p", {})
    warnings = " ".join(node.get("extra", {}).get("warnings", []))
    check("dados públicos sem rede: usa a leitura guardada, com o aviso e a data",
          code == 0 and node.get("status") == "executed" and "usando os dados lidos em 25/11/2026" in warnings,
          (code, node.get("status"), warnings[:200], err[-300:]))  # fmt: skip
    check(
        "a citação da fonte vai no resultado",
        node.get("extra", {}).get("fonte_publica", {}).get("citacao") == "Banco Central do Brasil, SGS 11",
    )
    code, out, err = run_offline("run", "selic_atual")
    check(
        "Exigir dados atuais sem rede: falha com o motivo",
        code != 0 and "Banco Central" in (out + err),
        (code, (out + err)[-300:]),
    )
    code, out, err = run_offline("run", "feriados_sp", "--relatorio", str(data / "feriados.json"))
    report = (
        json.loads((data / "feriados.json").read_text(encoding="utf-8"))
        if (data / "feriados.json").is_file()
        else {}
    )
    status = report.get("node_results", {}).get("p", {}).get("status")
    check(
        "feriados calculados no executável, sem rede (tabelas no pacote)",
        code == 0 and status == "executed",
        (code, status, err[-300:]),
    )
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
