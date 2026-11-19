"""Testes no ritmo certo (spec 043).

    uv run python scripts/testar.py            # rodada rápida (padrão)
    uv run python scripts/testar.py completo   # toda a suíte, em paralelo
    uv run python scripts/testar.py rapido -x  # o que vier depois do modo vai direto para o pytest

Rodada rápida:
  1. pytest-testmon roda só os testes que usam o código Python alterado desde a última rodada, sem os marcados
     `lento` (os que executam o fluxo de exemplo inteiro ou levam vários segundos), em paralelo. A primeira vez
     roda todos os não lentos para montar a base (.testmondata, fora do git). Os lentos saem por --sem-lentos
     (opção do tests/conftest.py), não por -m: com -m, o testmon desliga a seleção.
  2. O testmon não enxerga JS, CSS e HTML: se algo em src/prodata/web/ mudou (em relação ao último commit), roda
     também os testes que leem esses arquivos.

Rodada completa: todos os testes, inclusive os lentos, divididos entre os núcleos (pytest-xdist). É a que vale
antes de uma release; o CI roda a mesma a cada push.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = "src/prodata/web/"
# Testes que leem os arquivos da interface (tema, textos, Manual, filtros do dashboard, qualidade do código).
FRONT_TESTS = [
    "tests/test_theme.py",
    "tests/test_code_quality.py",
    "tests/test_language.py",
    "tests/test_manual.py",
    "tests/test_brand.py",
    "tests/test_polish.py",
    "tests/test_dash_filters.py",
]


def changed_files() -> list[str]:
    """Arquivos alterados em relação ao último commit, inclusive os novos ainda fora do git."""
    out: list[str] = []
    for cmd in (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S603
        out += [line.strip() for line in res.stdout.splitlines() if line.strip()]
    return out


def pytest(*args: str) -> int:
    print(f"\n$ pytest {' '.join(args)}", flush=True)
    return subprocess.run([sys.executable, "-m", "pytest", *args], cwd=ROOT, check=False).returncode  # noqa: S603


def quick(extra: list[str]) -> int:
    # 5 = nenhum teste selecionado (nada mudou): não é falha.
    code = pytest("--testmon", "--sem-lentos", "-n", "auto", *extra)
    status = 0 if code in (0, 5) else code
    if any(f.startswith(WEB) for f in changed_files()):
        print("\nA interface mudou (src/prodata/web): rodando também os testes que leem esses arquivos.")
        front = pytest("-n", "auto", *extra, *FRONT_TESTS)
        status = status or front
    return status


def full(extra: list[str]) -> int:
    return pytest("-n", "auto", *extra)


def main() -> int:
    args = sys.argv[1:]
    # Sem modo (ou começando por uma opção do pytest): rodada rápida, e tudo vai para o pytest.
    mode = args.pop(0) if args and not args[0].startswith("-") else "rapido"
    if mode not in ("rapido", "completo"):
        print(__doc__)
        return 2
    extra = args
    return quick(extra) if mode == "rapido" else full(extra)


if __name__ == "__main__":
    raise SystemExit(main())
