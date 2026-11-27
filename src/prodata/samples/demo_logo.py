"""Logo do dashboard do exemplo: segue a marca ativa (spec 036)."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from prodata.brand import marca

LOGO = marca().dir / "logo-claro.svg"
# Logos que o exemplo já usou, pelo SHA-256 do SVG sem "\r". O programa instalado só traz a pasta da marca ativa,
# então os logos das outras marcas não estão em disco: sem estas impressões, o da Protege nunca sairia da Desata.
KNOWN_LOGOS = frozenset(
    {
        "4d74ffb8d0c1fc758b40f43c988bdea0648f4a0449b80f3001779ced8cf1b1f5",  # Protege (escudo)
        "8b9619b2e7b025d8eea47a5b78e823105224aa691efb73a742d18767a58818ee",  # Protege, tema escuro (até a 0.9.6)
        "fe8ebef26539af83441fb898b17f00eb7b12676427010332de32d8b3d617ca43",  # Protege, tema escuro (branco)
        "b8cc2edc87dd8e4e7bc86107a7d4b60460a1479ccf65b6db2c526182b05bcf90",  # Desata
        "3d28b860ecb9f463f046cf4e463fd330c46eab625a7fa4407bf1a1244a858fef",  # Desata, tema escuro
        "ee90e88f2463ab27c16fb874557748aa11fd2ca26af6930f9096491954cbe2f1",  # neutra
        "4ad26ec6883855200325d24f58cffab460b9c5af551a8efe0f50c8bd718a1828",  # neutra, tema escuro
    }
)


def refresh_demo_logo(workflow: dict[str, Any]) -> bool:
    """O logo do dashboard do exemplo segue a marca ativa. Só troca se ainda é o logo de alguma marca: uma imagem
    que a pessoa colocou no lugar fica."""
    dashboard = workflow.get("dashboard") or {}
    logo = next(
        (i for i in dashboard.get("items", []) if i.get("id") == "d_logo" and i.get("kind") == "image"), None
    )
    if logo is None:
        return False
    active = logo_uri(LOGO)
    content = logo.get("content")
    if content != active and _is_brand_logo(content):
        logo["content"] = active
        return True
    return False


def _is_brand_logo(content: Any) -> bool:
    prefix = "data:image/svg+xml;base64,"
    if not isinstance(content, str) or not content.startswith(prefix):
        return False
    try:
        svg = base64.b64decode(content[len(prefix) :], validate=True)
    except ValueError:
        return False
    known = KNOWN_LOGOS | {_svg_digest(path.read_bytes()) for path in LOGO.parents[1].glob("*/logo-*.svg")}
    return _svg_digest(svg) in known


def _svg_digest(svg: bytes) -> str:
    return hashlib.sha256(svg.replace(b"\r", b"")).hexdigest()


def logo_uri(path: Any) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()
