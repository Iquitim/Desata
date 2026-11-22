"""Benchmark do motor (spec 048, RF-4841..4843): números de desempenho que qualquer um reproduz.

Gera dados de teste com semente fixa numa pasta temporária (100 mil, 1 milhão e 5 milhões de linhas), monta fluxos
típicos e executa pelo mesmo motor do CLI. Mede o tempo (mediana de três repetições, cada uma sem cache) e o pico de
memória do processo. Sem rede: nada sai do computador.

    uv run --with psutil python scripts/benchmark.py                    # tudo (alguns minutos)
    uv run --with psutil python scripts/benchmark.py --rapido           # só 100 mil linhas (confere que roda)
    uv run --with psutil python scripts/benchmark.py --saida resultados --comparar resultados/benchmark-0.9.4.json

Grava ``benchmark-<versão>-<data>.md`` e ``.json`` na pasta de ``--saida`` (padrão: a temporária). ``--comparar``
aponta o que ficou mais de 20% mais lento ou mais rápido que um resultado anterior.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
SIZES = (100_000, 1_000_000, 5_000_000)
REPEAT = 3
THRESHOLD = 0.20

try:  # memória: só com o psutil (uv run --with psutil)
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


# ---------------------------------------------------------------- dados


def make_data(folder: Path, rows: int) -> None:
    """Vendas com data, estado, produto, valor e quantidade; clientes por estado (para o Join). Semente fixa."""
    pl.set_random_seed(42)
    ufs = ["SP", "RJ", "MG", "PR", "RS", "BA", "SC", "PE", "GO", "DF"]
    base = pl.DataFrame({"i": pl.int_range(0, rows, eager=True)})
    sales = base.with_columns(
        (pl.col("i") % len(ufs)).replace_strict(dict(enumerate(ufs)), return_dtype=pl.String).alias("uf"),
        (pl.col("i") % 50).cast(pl.String).alias("produto"),
        (pl.date(2026, 1, 1) + pl.duration(days=pl.col("i") % 365)).alias("data"),
        ((pl.col("i") * 7919) % 100_000 / 100).alias("valor"),
        ((pl.col("i") % 9) + 1).alias("quantidade"),
    ).drop("i")
    sales.write_csv(folder / f"vendas_{rows}.csv")
    pl.DataFrame({"uf": ufs, "regiao": ["SE", "SE", "SE", "S", "S", "NE", "S", "NE", "CO", "CO"]}).write_csv(
        folder / "regioes.csv"
    )


# ---------------------------------------------------------------- fluxos


def _node(node_id: str, kind: str, **config: Any) -> dict[str, Any]:
    return {"id": node_id, "type": kind, "config": config}


def _edge(source: str, target: str, sh: str = "out", th: str = "in") -> dict[str, Any]:
    return {
        "id": f"{source}_{target}_{th}",
        "source": source,
        "sourceHandle": sh,
        "target": target,
        "targetHandle": th,
    }


def flows(rows: int, out_dir: Path) -> dict[str, dict[str, Any]]:
    data = f"vendas_{rows}.csv"
    src = _node("vendas", "io.input_data", dataset=data)
    reg = _node("regioes", "io.input_data", dataset="regioes.csv")
    filt = _node("filtro", "prep.filter", mode="expression", expression="[valor] > 500")
    form = _node(
        "conta",
        "prep.formula",
        formulas=[
            {"target": "new", "column": "total", "type": "Auto", "expression": "[valor] * [quantidade]"}
        ],
    )
    join = _node("junta", "transform.join", keys=[{"left": "uf", "right": "uf"}])
    summ = _node(
        "resumo",
        "transform.summarize",
        group_by=["regiao"],
        aggregations=[{"column": "total", "agg": "sum", "alias": "total"}],
    )
    sort = _node("ordena", "prep.sort", sorts=[{"column": "valor", "descending": True}])
    union = _node("empilha", "transform.union")
    out = _node(
        "saida",
        "io.output_data",
        filename="fechamento",
        folder=str(out_dir),
        format="csv",
        if_exists="replace",
    )
    return {
        "Ler CSV": {"nodes": [src], "edges": []},
        "Filter": {"nodes": [src, filt], "edges": [_edge("vendas", "filtro")]},
        "Formula": {"nodes": [src, form], "edges": [_edge("vendas", "conta")]},
        "Join": {"nodes": [src, reg, join], "edges": [_edge("vendas", "junta", th="L"), _edge("regioes", "junta", th="R")]},
        "Summarize": {"nodes": [src, form, summ | {"config": {"group_by": ["uf"], "aggregations": [{"column": "total", "agg": "sum", "alias": "total"}]}}],
                      "edges": [_edge("vendas", "conta"), _edge("conta", "resumo")]},
        "Union": {"nodes": [src, union], "edges": [_edge("vendas", "empilha", th="in1"), _edge("vendas", "empilha", th="in2")]},
        "Sort": {"nodes": [src, sort], "edges": [_edge("vendas", "ordena")]},
        "Fechamento inteiro": {
            "nodes": [src, reg, filt, form, join, summ, out],
            "edges": [_edge("vendas", "filtro"), _edge("filtro", "conta", sh="T"), _edge("conta", "junta", th="L"),
                      _edge("regioes", "junta", th="R"), _edge("junta", "resumo", sh="J"), _edge("resumo", "saida")],
        },
    }  # fmt: skip


# ---------------------------------------------------------------- medição


class PeakMemory:
    """Quanto a memória do processo subiu, no pico, enquanto mede (amostra a cada 20 ms)."""

    def __init__(self) -> None:
        self.peak = 0
        self.start = 0
        self._stop = threading.Event()
        self._proc = psutil.Process() if psutil else None

    def __enter__(self) -> PeakMemory:
        if self._proc is not None:
            self.start = self.peak = self._proc.memory_info().rss
            threading.Thread(target=self._watch, daemon=True).start()
        return self

    def _watch(self) -> None:
        while not self._stop.wait(0.02):
            self.peak = max(self.peak, self._proc.memory_info().rss)  # type: ignore[union-attr]

    def __exit__(self, *_: object) -> None:
        self._stop.set()


def measure(runner: Any, workflow_cls: Any, name: str, body: dict[str, Any], rows: int) -> dict[str, Any]:
    times, peaks = [], []
    for rep in range(REPEAT):  # cada repetição com outro id: sem resultado guardado (sem cache)
        wf = workflow_cls.model_validate(
            {"id": f"bench_{rows}_{abs(hash(name)) % 10_000}_{rep}", "name": name, **body}
        )
        with PeakMemory() as mem:
            started = time.perf_counter()
            report = runner.run(wf)
            elapsed = time.perf_counter() - started
        errors = [r.error for r in report.node_results.values() if r.status == "error"]
        if errors:
            raise SystemExit(f"{name} ({rows:,} linhas) falhou: {errors[0]}")
        times.append(elapsed)
        peaks.append(max(0, mem.peak - mem.start))
    return {"fluxo": name, "linhas": rows, "segundos": round(statistics.median(times), 3),
            "memoria_mb": round(max(peaks) / 1_048_576) if psutil else None}  # fmt: skip


def rerun(runner: Any, workflow_cls: Any, body: dict[str, Any], rows: int) -> dict[str, Any]:
    """Reexecutar sem mudanças: o motor só confere que nada mudou (execução incremental)."""
    wf = workflow_cls.model_validate({"id": f"bench_rerun_{rows}", "name": "Reexecutar", **body})
    runner.run(wf)
    times = []
    for _ in range(REPEAT):
        started = time.perf_counter()
        runner.run(wf)
        times.append(time.perf_counter() - started)
    return {
        "fluxo": "Reexecutar sem mudanças (fechamento)",
        "linhas": rows,
        "segundos": round(statistics.median(times), 3),
        "memoria_mb": None,
    }


def startup(storage: Path) -> dict[str, Any]:
    """Abrir o servidor do programa até ele responder (a parte do programa, sem a janela)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {
        **os.environ,
        "PRODATA_PORT": str(port),
        "PRODATA_STORAGE_DIR": str(storage / "abrir"),
        "PRODATA_SECRETS_BACKEND": "memory",
    }
    times = []
    for _ in range(REPEAT):
        started = time.perf_counter()
        proc = subprocess.Popen(
            [sys.executable, "-m", "prodata"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(600):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
                    break
                except OSError:
                    time.sleep(0.05)
            times.append(time.perf_counter() - started)
        finally:
            if sys.platform == "win32":
                kill = ["taskkill", "/T", "/F", "/PID", str(proc.pid)]  # o processo e os filhos dele
                subprocess.run(kill, capture_output=True, check=False)  # noqa: S603
            else:
                proc.terminate()
            proc.wait(timeout=30)
    return {
        "fluxo": "Abrir o servidor até responder",
        "linhas": 0,
        "segundos": round(statistics.median(times), 2),
        "memoria_mb": None,
    }


# ---------------------------------------------------------------- relatório


def machine() -> dict[str, Any]:
    info: dict[str, Any] = {"sistema": f"{platform.system()} {platform.release()}", "processador": platform.processor() or platform.machine(),
                            "nucleos": os.cpu_count(), "python": platform.python_version(), "polars": pl.__version__}  # fmt: skip
    if psutil:
        info["memoria_gb"] = round(psutil.virtual_memory().total / 1_073_741_824, 1)
    return info


def markdown(result: dict[str, Any], comparison: list[str]) -> str:
    m = result["maquina"]
    lines = [f"# Benchmark {result['versao']} · {result['data']}", "",
             f"{m['sistema']} · {m['processador']} · {m['nucleos']} núcleos" + (f" · {str(m['memoria_gb']).replace('.', ',')} GB" if m.get("memoria_gb") else "")
             + f" · Python {m['python']} · Polars {m['polars']}", "",
             "| Fluxo | Linhas | Tempo (s) | Memória a mais no pico (MB) |", "|---|---:|---:|---:|"]  # fmt: skip
    for r in result["medidas"]:
        rows = f"{r['linhas']:,}".replace(",", ".") if r["linhas"] else "—"
        lines.append(
            f"| {r['fluxo']} | {rows} | {str(r['segundos']).replace('.', ',')} | {r['memoria_mb'] or '—'} |"
        )
    lines += [
        "",
        "Mediana de três repetições, cada uma sem resultado guardado. Dados gerados com semente fixa.",
    ]
    if comparison:
        lines += ["", "## Comparado com o resultado anterior", "", *comparison]
    return "\n".join(lines) + "\n"


def compare(current: dict[str, Any], previous: dict[str, Any]) -> list[str]:
    before = {(r["fluxo"], r["linhas"]): r["segundos"] for r in previous.get("medidas", [])}
    out = []
    for r in current["medidas"]:
        old = before.get((r["fluxo"], r["linhas"]))
        if not old:
            continue
        change = (r["segundos"] - old) / old
        if abs(change) > THRESHOLD:
            word = "mais lento" if change > 0 else "mais rápido"
            out.append(
                f"- **{r['fluxo']}** ({r['linhas']:,} linhas): {abs(change):.0%} {word} ({old} s → {r['segundos']} s)".replace(
                    ",", "."
                )
            )
    return out


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        getattr(stream, "reconfigure", lambda **_: None)(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Benchmark do motor")
    parser.add_argument("--rapido", action="store_true", help="só 100 mil linhas")
    parser.add_argument("--saida", type=Path, default=None, help="pasta para o .md e o .json")
    parser.add_argument("--comparar", type=Path, default=None, help="JSON de um resultado anterior")
    args = parser.parse_args()
    sizes = SIZES[:1] if args.rapido else SIZES
    tmp = Path(tempfile.mkdtemp(prefix="benchmark-"))
    os.environ["PRODATA_STORAGE_DIR"] = str(tmp / "dados")
    os.environ["PRODATA_SECRETS_BACKEND"] = "memory"
    from prodata import __version__
    from prodata.config import Settings
    from prodata.domain.workflow import Workflow
    from prodata.main import build_services

    try:
        services = build_services(Settings())
        measures = [startup(tmp)]
        print(f"Abrir o servidor: {measures[0]['segundos']} s", flush=True)
        for rows in sizes:
            make_data(services.datasets.root, rows)
            for name, body in flows(rows, tmp / "saidas").items():
                (tmp / "saidas").mkdir(exist_ok=True)
                found = measure(services.runner, Workflow, name, body, rows)
                measures.append(found)
                print(
                    f"{name:<22} {rows:>9,} linhas  {found['segundos']:>7} s  {found['memoria_mb'] or '—'} MB",
                    flush=True,
                )
            measures.append(
                rerun(services.runner, Workflow, flows(rows, tmp / "saidas")["Fechamento inteiro"], rows)
            )
        result = {
            "versao": __version__,
            "data": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "maquina": machine(),
            "medidas": measures,
        }
        comparison = (
            compare(result, json.loads(args.comparar.read_text(encoding="utf-8"))) if args.comparar else []
        )
        out = args.saida or tmp
        out.mkdir(parents=True, exist_ok=True)
        stem = f"benchmark-{__version__}-{datetime.now().strftime('%Y%m%d-%H%M')}"
        (out / f"{stem}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / f"{stem}.md").write_text(markdown(result, comparison), encoding="utf-8")
        print(f"\nResultado: {out / stem}.md")
        for line in comparison:
            print(line)
        return 0
    finally:
        shutil.rmtree(tmp / "dados", ignore_errors=True)  # os dados gerados são grandes; o resultado fica


if __name__ == "__main__":
    raise SystemExit(main())
