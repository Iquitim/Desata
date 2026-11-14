"""Marca no guia (spec 036): troca as marcações de guia.html pelos dados e pela paleta da marca escolhida.

    --marca <id> em qualquer gerador do guia escolhe a marca; sem a opção, vale a marca ativa (PRODATA_MARCA ou padrão).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def choose_brand(argv: list[str] | None = None) -> None:
    """Lê ``--marca <id>`` da linha de comando antes de qualquer import do programa (a marca é lida uma vez)."""
    args = sys.argv if argv is None else argv
    if "--marca" in args:
        i = args.index("--marca")
        os.environ["PRODATA_MARCA"] = args[i + 1]
        del args[i : i + 2]


def values() -> dict[str, str]:
    from prodata.brand import marca, mix

    b = marca()
    light = b.light()
    org = b.organizacao or b.nome
    logo = (b.dir / "logo-escuro.svg").relative_to(ROOT).as_posix()
    return {
        "{{produto}}": b.nome,
        "{{nome_curto}}": b.nome_curto,
        "{{organizacao}}": org,
        "{{organizacao_capa}}": b.organizacao,
        "{{titulo_guia}}": f"{b.nome} — Guia do Produto" + (f" · {b.organizacao}" if b.organizacao else ""),
        "{{rodape_pdf}}": f"{b.title} · Guia do Produto",
        "{{logo_escuro}}": f"../../{logo}",
        "{{fonte}}": b.fonte_texto,
        "{{fonte_titulos}}": b.title_font,
        "{{capa_classe}}": "cover-centered" if b.capa == "centralizada" else "",
        "{{slogan}}": b.slogan,
        "{{fontes_marca}}": _font_faces(b),
        "{{gradiente_capa}}": _cover_gradient(b),
        "{{cor_barra}}": str(light.barra),
        "{{cor_barra_escura}}": str(light.realce_texto),
        "{{cor_barra_clara}}": mix(str(light.barra), str(light.foco), 0.5),
        "{{cor_destaque_fraco}}": str(light.destaque_fraco),
        "{{cor_org}}": str(light.organizacao),
        "{{cor_botao}}": str(light.botao),
        "{{cor_realce}}": str(light.realce),
    }


def _cover_gradient(b) -> str:  # noqa: ANN001
    """Capa: o gradiente de identidade da marca, em diagonal (sem ele, a barra escurecendo, como na 0.7.7)."""
    colors = b.identity_gradient()
    if not b.gradiente:
        return f"linear-gradient(160deg, {colors[0]} 0%, {colors[1]} 55%, {colors[2]} 100%)"
    stops = ", ".join(f"{c} {round(i * 100 / (len(colors) - 1))}%" for i, c in enumerate(colors))
    return f"linear-gradient(160deg, {stops})"


def _font_faces(b) -> str:  # noqa: ANN001
    """@font-face das fontes que vêm no pacote da marca (como a Manrope da Desata)."""
    from prodata.brand import _range, font_files

    rules = []
    for name, family in font_files(b).items():
        url = f"../../{(b.dir / 'fontes' / name).relative_to(ROOT).as_posix()}"
        rules.append(
            f"  @font-face {{ font-family: '{family}'; font-weight: 200 800; src: url('{url}') format('woff2');{_range(name)} }}"
        )
    return "\n".join(rules)


def render(html: str) -> str:
    for key, value in values().items():
        html = html.replace(key, value)
    return html


def pdf_name() -> str:
    from prodata.brand import marca

    return f"{marca().nome_curto}-Guia-do-Produto.pdf"
