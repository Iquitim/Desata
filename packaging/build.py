"""Build do aplicativo de desktop (spec 008).

    uv run python packaging/build.py                 # marca padrão: ícone + executável + zip + instalador
    uv run python packaging/build.py --marca neutra  # outra marca (spec 036)
    uv run python packaging/build.py --no-setup      # sem o instalador

Saídas em dist/: <nome curto>/ (pasta do app), <nome curto>-<versão>-portable.zip e
<nome curto>-<versão>-setup.exe.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from prodata.brand import DEFAULT, Brand, check, load

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"
DIST = ROOT / "dist"

ISCC_CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
]


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def step(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


def write_version_info(ver: str, brand: Brand) -> None:
    """Metadados do .exe (Propriedades > Detalhes no Windows Explorer)."""
    parts = [*map(int, ver.split(".")), 0, 0, 0][:4]
    tup = ", ".join(map(str, parts))
    (PACKAGING / "version_info.txt").write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup})),
  kids=[StringFileInfo([StringTable('041604B0', [
    StringStruct('CompanyName', '{brand.publisher}'),
    StringStruct('FileDescription', '{brand.nome} - pipelines de dados visuais'),
    StringStruct('FileVersion', '{ver}'),
    StringStruct('ProductName', '{brand.nome}'),
    StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])]
)
""",
        encoding="utf-8",
    )


def check_prints(base: Path, brand_id: str) -> None:
    """Spec 046: o Manual do pacote só leva prints desta versão e desta marca, feitos todos na mesma geração."""
    manifest = base / "prints.json"
    info = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    if info.get("versao") != version() or info.get("marca") != brand_id:
        sys.exit(
            f"Os prints em {base} são da versão {info.get('versao', '?')}, marca {info.get('marca', '?')}; o build é da "
            f"{version()}, marca {brand_id}. Rode a geração completa (docs/guia/imagens/gerar_imagens.py, sem IMAGENS_SO)."
        )


def manual_images(brand: Brand, app_dir: Path, ready: Path | None = None) -> None:
    """Marca que não é a padrão: os prints do Manual no repositório mostram a padrão, então são refeitos (spec 036).

    ``ready``: pasta com prints já feitos para esta marca (img/ e img-escuro/), sem refazer.
    """
    if brand.id == DEFAULT:
        check_prints(ROOT / "src/prodata/web/manual", brand.id)
        return
    step(f"Prints do Manual com a marca {brand.id}")
    target = next(app_dir.rglob("web/manual"))
    if ready is not None:
        check_prints(ready, brand.id)
        for theme in ("img", "img-escuro"):
            shutil.copytree(ready / theme, target / theme, dirs_exist_ok=True)
        return
    with tempfile.TemporaryDirectory(prefix="prodata-prints-") as tmp:
        subprocess.run(
            ["uv", "run", "--with", "playwright", "--with", "pillow", "python",
             str(ROOT / "docs/guia/imagens/gerar_imagens.py"), "--marca", brand.id, "--saida", tmp],
            check=True, cwd=ROOT,
        )  # fmt: skip
        for theme in ("img", "img-escuro"):
            shutil.copytree(Path(tmp) / theme, target / theme, dirs_exist_ok=True)


def build_exe() -> None:
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(PACKAGING / "prodata.spec"),
         "--noconfirm", "--clean", "--distpath", str(DIST), "--workpath", str(ROOT / "build")],
        check=True,
    )  # fmt: skip


def build_zip(ver: str, brand: Brand) -> Path:
    base = DIST / f"{brand.nome_curto}-{ver}-portable"
    return Path(shutil.make_archive(str(base), "zip", root_dir=DIST, base_dir=brand.nome_curto))


def build_setup(ver: str, brand: Brand) -> Path | None:
    iscc = next((p for p in ISCC_CANDIDATES if p.is_file()), None) or shutil.which("ISCC")
    if not iscc:
        print(
            "Inno Setup não encontrado (instale com: winget install JRSoftware.InnoSetup). Pulando o instalador."
        )
        return None
    subprocess.run(
        [
            str(iscc),
            f"/DAppVersion={ver}",
            f"/DSourceDir={DIST / brand.nome_curto}",
            f"/DAppId={brand.instalacao.app_id}",
            f"/DAppName={brand.nome}",
            f"/DShortName={brand.nome_curto}",
            f"/DPublisher={brand.publisher}",
            str(PACKAGING / "installer.iss"),
        ],
        check=True,
    )
    return DIST / f"{brand.nome_curto}-{ver}-setup.exe"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--no-setup", action="store_true", help="não gerar o instalador")
    parser.add_argument(
        "--prints", type=Path, default=None, help="pasta com os prints do Manual já feitos para a marca"
    )
    parser.add_argument(
        "--marca", default=None, help=f"marca do programa (padrão: {DEFAULT}); veja src/prodata/marcas/"
    )
    args = parser.parse_args()
    os.environ["PRODATA_MARCA"] = args.marca or os.environ.get("PRODATA_MARCA") or DEFAULT

    step("Marca")
    brand = load(os.environ["PRODATA_MARCA"])
    for warning in check(brand):
        print(f"Aviso: {warning}")
    print(f"{brand.id}: {brand.title}")
    app_dir = DIST / brand.nome_curto

    ver = version()
    step("Ícone e metadados")
    subprocess.run([sys.executable, str(PACKAGING / "make_icon.py")], check=True)
    write_version_info(ver, brand)

    step("Executável (PyInstaller)")
    shutil.rmtree(app_dir, ignore_errors=True)
    build_exe()
    manual_images(brand, app_dir, args.prints)

    step("Pacote portátil (.zip)")
    zip_path = build_zip(ver, brand)

    setup_path = None
    if not args.no_setup:
        step("Instalador (Inno Setup)")
        setup_path = build_setup(ver, brand)

    size = sum(f.stat().st_size for f in app_dir.rglob("*") if f.is_file()) / 2**20
    step("Pronto")
    print(f"App:         {app_dir}  ({size:.0f} MB)")
    print(f"Portátil:    {zip_path}  ({zip_path.stat().st_size / 2**20:.0f} MB)")
    if setup_path:
        print(f"Instalador:  {setup_path}  ({setup_path.stat().st_size / 2**20:.0f} MB)")


if __name__ == "__main__":
    main()
