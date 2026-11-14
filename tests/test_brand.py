"""Spec 036: marca configurável. Pacotes, paleta, rotas, marca neutra, mudança de marca e código sem marca fixa."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from prodata import brand
from prodata.brand import BrandError, contrast
from prodata.brand_migration import MARKER, copy_data, copy_secrets, remember, secret_keys, source_for
from prodata.connectors.secrets import INSTALLATION_KEY, MemorySecretStore

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "prodata"
PROTEGE_COLORS = ("#043154", "#03223a", "#95793c", "#866c33", "#74602d", "#c9b27c", "#095d9e")


# ------------------------------------------------------------------ pacotes


def test_both_brands_load_and_pass_the_check() -> None:
    assert {"protege", "neutra", "desata"} <= set(brand.available())
    for brand_id in ("protege", "neutra", "desata"):
        warnings = brand.check(brand.load(brand_id))
        assert all(w.startswith("série") for w in warnings), warnings


def test_protege_keeps_the_identity_of_0_7_7() -> None:
    b = brand.load("protege")
    light, dark = b.light(), b.dark()
    assert (b.nome, b.organizacao, b.data_folder, b.vault_service) == (
        "PRO.DATA",
        "Grupo Protege",
        "PRO.DATA",
        "PRODATA",
    )
    assert b.instalacao.app_id == "6C1C7E0B-4F9B-4B2A-9C1E-7E3B9D2A5F10"
    assert (light.barra, light.botao, light.organizacao, light.destaque) == (
        "#043154",
        "#866c33",
        "#95793c",
        "#043154",
    )
    assert (dark.barra, dark.botao, dark.destaque) == (
        "#21222c",
        "#ffb86c",
        None,
    )  # destaque escuro: o do tema


def test_neutral_brand_derives_the_palette_with_contrast() -> None:
    b = brand.load("neutra")
    light = b.light()
    assert b.organizacao == "" and b.title == "Neutro" and b.vault_service == "NEUTRO"
    for fg, bg in (("barra_texto", "barra"), ("botao_texto", "botao"), ("destaque_texto", "destaque")):
        assert contrast(getattr(light, fg), getattr(light, bg)) >= 4.5
    css = brand.css(b)
    assert "--marca-barra: #1f2937;" in css and ':root[data-theme="dark"]' in css and "--series-1" not in css


def write_brand(tmp_path: Path, toml: str, files: bool = True) -> Path:
    folder = tmp_path / "teste"
    folder.mkdir()
    (folder / "marca.toml").write_text(toml, encoding="utf-8")
    if files:
        for name in brand.FILES:
            (folder / name).write_bytes(b"x")
    return folder


BASE = 'nome = "Teste"\nnome_curto = "Teste"\n[instalacao]\napp_id = "11111111-2222-3333-4444-555555555555"\n'


@pytest.mark.parametrize(
    ("colors", "message"),
    [
        ('[cores.claro]\nbarra = "azul"\ndestaque = "#2a63d6"\n', "cor inválida"),
        ('[cores.claro]\ndestaque = "#2a63d6"\n', "barra"),
        (
            '[cores.claro]\nbarra = "#ffffff"\nbarra_texto = "#eeeeee"\ndestaque = "#2a63d6"\n',
            "texto da barra",
        ),
    ],
)
def test_check_explains_what_to_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, colors: str, message: str
) -> None:
    monkeypatch.setattr(brand, "MARCAS_DIR", tmp_path)
    write_brand(tmp_path, BASE + colors)
    with pytest.raises(BrandError, match=message):
        brand.check(brand.load("teste"))


def test_missing_file_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(brand, "MARCAS_DIR", tmp_path)
    write_brand(tmp_path, BASE + '[cores.claro]\nbarra = "#1f2937"\ndestaque = "#2a63d6"\n', files=False)
    with pytest.raises(BrandError, match=r"falta o arquivo logo-claro.svg"):
        brand.check(brand.load("teste"))


# ------------------------------------------------------------------ servidor (marca padrão: protege)


def test_page_and_brand_routes(client: TestClient) -> None:
    active = brand.marca()
    page = client.get("/").text
    assert f"<title>{active.title}</title>" in page and f'data-marca-nome="{active.nome}"' in page
    assert "{{marca." not in page and 'src="/marca/logo-escuro.svg"' in page
    css = client.get("/marca/cores.css")
    assert css.status_code == 200 and f"--marca-barra: {active.light().barra};" in css.text
    assert client.get("/marca/logo-claro.svg").headers["content-type"].startswith("image/svg+xml")
    assert client.get("/marca/marca.toml").status_code == 404
    assert client.get("/marca/fontes/..%2Fmarca.toml").status_code == 404
    assert client.get("/api/marca").json()["nome"] == active.nome


def test_desata_is_the_default_brand() -> None:
    assert brand.DEFAULT == "desata"


# ------------------------------------------------------------------ marca neutra, de ponta a ponta

NEUTRAL_SCRIPT = """
import json, sys
from fastapi.testclient import TestClient
from prodata.config import Settings
from prodata.main import create_app
from prodata.desktop import _window_title, user_data_dir
from prodata.connectors.secrets import SERVICE
with TestClient(create_app(Settings(storage_dir=sys.argv[1], allowed_hosts=["testserver"]))) as c:
    out = {"page": c.get("/").text, "css": c.get("/marca/cores.css").text, "catalog": json.dumps(c.get("/api/catalog").json(), ensure_ascii=False),
           "title": _window_title(), "data": str(user_data_dir()), "service": SERVICE, "marca": c.get("/api/marca").json()}
print(json.dumps(out, ensure_ascii=False))
"""


def test_neutral_brand_never_mentions_protege(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "PRODATA_MARCA": "neutra",
        "PRODATA_SECRETS_BACKEND": "memory",
        "PYTHONIOENCODING": "utf-8",
    }
    run = subprocess.run(
        [sys.executable, "-c", NEUTRAL_SCRIPT, str(tmp_path / "dados")],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=180, check=True,
    )  # fmt: skip
    out = json.loads(run.stdout.strip().splitlines()[-1])
    everything = json.dumps(out, ensure_ascii=False)
    assert "Protege" not in everything and "PRO.DATA" not in everything and "#043154" not in everything
    assert "<title>Neutro</title>" in out["page"] and "Neutro" in out["catalog"]
    assert (
        out["title"].startswith("Neutro ") and out["data"].endswith("Neutro") and out["service"] == "NEUTRO"
    )
    assert out["marca"]["organizacao"] == ""


# ------------------------------------------------------------------ mudança de marca


def test_migration_offer_copy_and_secrets(tmp_path: Path) -> None:
    old = tmp_path / "PRO.DATA"
    (old / "workflows").mkdir(parents=True)
    (old / "workflows" / "fluxo.prodata.json").write_text("{}", encoding="utf-8")
    (old / "cache").mkdir()
    (old / "cache" / "grande.arrow").write_bytes(b"x")
    (old / "connections.json").write_text(
        json.dumps(
            [{"id": "erp", "name": "ERP", "kind": "postgres", "host": "h", "database": "d", "user": "u"}]
        ),
        encoding="utf-8",
    )
    target = brand.load("neutra").model_copy(
        update={
            "instalacao": brand.load("neutra").instalacao.model_copy(
                update={"migrar_de": [{"pasta": "PRO.DATA", "cofre": "PRODATA"}]}
            )
        }
    )
    new = tmp_path / "Neutro"
    source = source_for(target, new)
    assert source is not None and source.folder == old and source.service == "PRODATA"
    copy_data(source.folder, new)
    assert (new / "workflows" / "fluxo.prodata.json").is_file() and not (new / "cache").exists()
    assert (old / "cache" / "grande.arrow").is_file()  # a pasta antiga fica intacta
    keys = secret_keys(new)
    assert INSTALLATION_KEY in keys and "connection:erp" in keys
    before, after = MemorySecretStore(), MemorySecretStore()
    before.set("connection:erp", "senha")
    before.set(INSTALLATION_KEY, "ab" * 32)
    copied, missing = copy_secrets(keys, before, after)
    assert copied == 2 and missing == [] and after.get("connection:erp") == "senha"
    remember(new, source, data=True, secrets=True, missing=[])
    assert (new / MARKER).is_file() and source_for(target, new) is None


# ------------------------------------------------------------------ código sem marca fixa (RF-3640)


def _python_strings(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docs.add(id(first.value))
    return [
        (n.lineno, n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
    ]


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(^|[^:'\"`\\])//[^\n]*", r"\1", text)


def test_code_has_no_fixed_brand() -> None:
    found: list[str] = []
    marcas = SRC / "marcas"
    for path in SRC.rglob("*.py"):
        if marcas in path.parents:
            continue
        for line, value in _python_strings(path):
            if "PRO.DATA" in value or "Protege" in value:
                found.append(f"{path.relative_to(SRC)}:{line}: {value[:60]!r}")
    for path in [
        *(SRC / "web" / "js").glob("*.js"),
        SRC / "web" / "index.html",
        *(SRC / "web" / "css").glob("*.css"),
    ]:
        text = path.read_text(encoding="utf-8")
        code = (
            _strip_js_comments(text) if path.suffix == ".js" else re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        )
        for word in ("PRO.DATA", "Protege", "protege-escudo", *PROTEGE_COLORS):
            if word.lower() in code.lower():
                found.append(f"{path.relative_to(SRC)}: {word}")
    for path in (ROOT / "packaging").glob("*"):
        if path.suffix in (".py", ".iss", ".spec") and ("Protege" in path.read_text(encoding="utf-8")):
            found.append(f"packaging/{path.name}: Protege")
    assert not found, "\n".join(found)


def test_desata_uses_its_identity_and_keeps_status_colors_readable() -> None:
    """Spec 036, etapa 2: paleta da Desata; as cores funcionais do tema seguem legíveis sobre os neutros dela."""
    b = brand.load("desata")
    light, dark = b.light(), b.dark()
    assert (b.nome, b.title, b.title_font, b.vault_service) == ("Desata", "Desata", "Manrope", "DESATA")
    assert (light.barra, light.botao, light.organizacao, light.fundo) == (
        "#003F46",
        "#007E7D",
        "#21C7A4",
        "#F5F8F8",
    )
    assert set(brand.font_files(b).values()) == {"Manrope"} and "--font-title: 'Manrope'" in brand.css(b)
    tokens = (ROOT / "src/prodata/web/css/tokens.css").read_text(encoding="utf-8")
    status_re = r"--(ok|warn|err):\s*(#[0-9a-fA-F]{6})"
    themes = [
        (light, dict(re.findall(status_re, tokens.split("@media")[0]))),
        (dark, dict(re.findall(status_re, tokens[tokens.index(':root[data-theme="dark"]') :]))),
    ]
    for palette, status in themes:
        assert len(status) == 3
        for color in status.values():
            for bg in ("fundo", "superficie", "superficie_2", "superficie_3"):
                assert contrast(color, getattr(palette, bg)) >= 4.5, (color, bg)
