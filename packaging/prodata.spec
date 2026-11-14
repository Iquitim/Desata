# PyInstaller: aplicativo de desktop em pasta única (spec 008). Uso: uv run python packaging/build.py [--marca <id>]
# ruff: noqa
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

from prodata.brand import marca

HERE = SPECPATH  # noqa: F821 (injetado pelo PyInstaller)
BRAND = marca()  # escolhida pelo build.py em PRODATA_MARCA (spec 036)
# A marca do pacote fica gravada nele: o programa instalado tem uma marca só.
ACTIVE = Path(workpath) / "_ativa.txt"  # noqa: F821
ACTIVE.parent.mkdir(parents=True, exist_ok=True)
ACTIVE.write_text(BRAND.id, encoding="utf-8")


def _other_brand(dest: str) -> bool:
    parts = Path(dest).parts
    return "marcas" in parts and parts[parts.index("marcas") + 1:][:1] not in ((BRAND.id,), ())

hiddenimports = (
    collect_submodules("prodata")  # ferramentas são registradas por import
    + collect_submodules("uvicorn")  # loops/protocolos escolhidos em tempo de execução
    + collect_submodules("webview")
    + collect_submodules("sklearn.ensemble")
    + collect_submodules("sklearn.linear_model")
    + collect_submodules("sqlglot")  # dialetos escolhidos por nome (spec 033)
    + collect_submodules("skops")  # arquivo .modelo, sem pickle (spec 033)
    + ["keyring.backends.Windows", "sklearn.utils._typedefs", "sklearn.neighbors._partition_nodes", "pyodbc"]
)

datas = (
    [d for d in collect_data_files("prodata") if not _other_brand(d[1]) and not d[0].endswith("LEIA-ME.md")]  # interface web e só a marca escolhida
    + [(str(ACTIVE), "prodata/marcas")]
    + collect_data_files("webview")
    + collect_data_files("sklearn")
    # Bibliotecas que leem a própria versão ou usam entry points (keyring acha o cofre do Windows assim).
    + [m for pkg in ("connectorx", "keyring", "polars", "duckdb", "fastexcel", "pywebview", "fastapi",
                     "uvicorn", "pydantic", "scikit-learn", "pyarrow", "xlsxwriter")
       for m in copy_metadata(pkg)]
)

a = Analysis(  # noqa: F821
    # Dois pontos de entrada no mesmo pacote: a janela e a linha de comando (spec 033).
    [f"{HERE}/launcher.py", f"{HERE}/launcher_cli.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "IPython", "pytest", "mypy", "ruff", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
# Tela de abertura (spec 018): aparece logo no clique, antes de carregar o motor de dados.
# O desktop.py atualiza o texto de andamento e fecha a tela quando a janela principal aparece.
splash = Splash(  # noqa: F821
    f"{HERE}/splash.png",
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(203, 262),
    text_size=10,
    text_color=str(BRAND.light().barra_suave).upper(),
    text_default="Abrindo…",
    always_on_top=False,
)
window_scripts = [s for s in a.scripts if s[0] != "launcher_cli"]
cli_scripts = [s for s in a.scripts if s[0] != "launcher"]
exe = EXE(  # noqa: F821
    pyz,
    splash,
    window_scripts,
    [],
    exclude_binaries=True,
    name=BRAND.nome_curto,
    console=False,  # sem janela de terminal
    icon=f"{HERE}/prodata.ico",
    version=f"{HERE}/version_info.txt",
)
# Linha de comando (spec 033): mesmo pacote, com console e sem tela de abertura. Serve ao Agendador do Windows.
cli_exe = EXE(  # noqa: F821
    pyz,
    cli_scripts,
    [],
    exclude_binaries=True,
    name="prodata-cli",
    console=True,
    icon=f"{HERE}/prodata.ico",
    version=f"{HERE}/version_info.txt",
)
coll = COLLECT(  # noqa: F821
    exe, cli_exe, a.binaries, a.datas, splash.binaries, name=BRAND.nome_curto
)
