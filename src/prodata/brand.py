"""Marca configurável (spec 036): nome, organização, paleta, logos e onde o programa guarda coisas.

Cada marca é uma pasta em ``prodata/marcas/<id>/`` com ``marca.toml`` e os arquivos visuais. A marca ativa vem de
``PRODATA_MARCA``, senão do ``_ativa.txt`` que o build grava no pacote, senão da marca padrão do repositório.
Identificadores técnicos (pacote ``prodata``, ``PRODATA_*``, ``.prodata.json``) não dependem da marca.
"""

from __future__ import annotations

import os
import re
import tomllib
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MARCAS_DIR = Path(__file__).resolve().parent / "marcas"
DEFAULT = "desata"  # marca padrão do repositório (spec 036, decisão 3; Desata desde a 0.8.0)
ACTIVE_FILE = MARCAS_DIR / "_ativa.txt"
FILES = ("logo-claro.svg", "logo-escuro.svg", "icone.png")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
WHITE, INK = "#ffffff", "#1b1b19"
# Fundos do tema onde os gráficos aparecem: para conferir o contraste das séries.
SURFACE = {"claro": "#ffffff", "escuro": "#282a36"}
FONTS = ("Open Sans", "Inter", "JetBrains Mono")  # empacotadas com o app (fonts.css)


class BrandError(ValueError):
    """Pacote de marca com problema: a mensagem diz o que corrigir."""


# ------------------------------------------------------------------ cores


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def mix(a: str, b: str, t: float) -> str:
    """``t`` de ``a`` e o resto de ``b``."""
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02x}" for x, y in zip(ra, rb, strict=True))


def _luminance(color: str) -> float:
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_on(background: str) -> str:
    return WHITE if contrast(WHITE, background) >= contrast(INK, background) else INK


# ------------------------------------------------------------------ modelo


class Palette(BaseModel):
    """Papéis da paleta num tema. Só barra e destaque são obrigatórios no claro; o resto sai deles."""

    barra: str | None = None
    barra_borda: str | None = None
    barra_texto: str | None = None
    barra_suave: str | None = None
    selecao_fundo: str | None = None
    selecao_texto: str | None = None
    realce: str | None = None
    realce_texto: str | None = None
    botao: str | None = None
    botao_hover: str | None = None
    botao_texto: str | None = None
    organizacao: str | None = None
    destaque: str | None = None
    destaque_hover: str | None = None
    destaque_fraco: str | None = None
    destaque_texto: str | None = None
    foco: str | None = None
    series: list[str] | None = None
    # Neutros (opcionais, os quatro juntos): sem eles, valem os do tema.
    fundo: str | None = None
    superficie: str | None = None
    bordas: str | None = None
    texto: str | None = None
    # Saem dos neutros; não precisam estar no marca.toml.
    superficie_2: str | None = None
    superficie_3: str | None = None
    tela: str | None = None
    tela_ponto: str | None = None
    bordas_fortes: str | None = None
    texto_2: str | None = None
    texto_3: str | None = None

    @field_validator("*")
    @classmethod
    def _hex(cls, value: object) -> object:
        values = value if isinstance(value, list) else [value]
        for v in values:
            if v is not None and not (isinstance(v, str) and HEX.match(v)):
                raise ValueError(f"cor inválida: {v!r} (use #rrggbb)")
        return value

    @field_validator("series")
    @classmethod
    def _eight(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != 8:
            raise ValueError("a paleta de gráficos precisa de 8 cores")
        return value


# Escuro sem definição na marca: a barra escura do tema, com destaque e séries do próprio tema.
DARK_BAR = Palette(
    barra="#21222c",
    barra_borda="#44475a",
    barra_texto=WHITE,
    barra_suave="#c8d6e5",
    selecao_fundo="#44475a",
    selecao_texto="#f8f8f2",
    botao="#bd93f9",
    botao_hover="#cfaefb",
    botao_texto="#21222c",
    organizacao="#bd93f9",
)


class Install(BaseModel):
    app_id: str = Field(
        pattern=r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
    )
    editora: str = ""
    pasta_dados: str = ""
    cofre: str = ""
    migrar_de: list[dict[str, str]] = Field(default_factory=list)


class Brand(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,30}$")
    nome: str = Field(min_length=1, max_length=40)
    nome_curto: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,30}$")
    organizacao: str = Field("", max_length=60)
    apoio: str = Field("", max_length=60)
    site: str = ""
    rodape: str = Field("", max_length=200)
    fonte_texto: str = "Open Sans"
    fonte_titulos: str = ""  # vazio: os títulos usam a fonte do texto
    fonte_codigo: str = "JetBrains Mono"
    slogan: str = Field("", max_length=80)
    # Fundos de identidade (abertura, instalador, capa do guia), em diagonal. Vazio: barra escurecendo.
    gradiente: list[str] = Field(default_factory=list, max_length=3)
    # Capa do guia: "padrao" (logo e nome à esquerda, como na 0.7.7) ou "centralizada" (logo grande ao centro).
    capa: Literal["padrao", "centralizada"] = "padrao"
    instalacao: Install
    claro: Palette
    escuro: Palette | None = None

    @field_validator("gradiente")
    @classmethod
    def _gradient(cls, value: list[str]) -> list[str]:
        if value and (len(value) < 2 or not all(HEX.match(c) for c in value)):
            raise ValueError("gradiente: 2 ou 3 cores no formato #rrggbb")
        return value

    @property
    def title_font(self) -> str:
        return self.fonte_titulos or self.fonte_texto

    @property
    def dir(self) -> Path:
        return MARCAS_DIR / self.id

    @property
    def data_folder(self) -> str:
        return self.instalacao.pasta_dados or self.nome_curto

    @property
    def vault_service(self) -> str:
        return self.instalacao.cofre or re.sub(r"[^A-Z0-9]", "", self.nome_curto.upper())

    @property
    def publisher(self) -> str:
        return self.instalacao.editora or self.organizacao or self.nome

    @property
    def title(self) -> str:
        """ "PRO.DATA · Grupo Protege", ou só o nome quando não há organização."""
        return f"{self.nome} · {self.organizacao}" if self.organizacao else self.nome

    @property
    def tagline(self) -> str:
        """Linha embaixo do nome na barra superior."""
        return self.apoio or self.organizacao

    def light(self) -> Palette:
        return _complete_light(self.claro)

    def dark(self) -> Palette:
        return _complete_dark(self.escuro, self.light())

    def public(self) -> dict[str, str]:
        """O que a tela precisa saber da marca."""
        return {"nome": self.nome, "nome_curto": self.nome_curto, "organizacao": self.organizacao,
                "apoio": self.tagline, "site": self.site, "rodape": self.rodape, "slogan": self.slogan}  # fmt: skip

    def identity_gradient(self) -> list[str]:
        """Cores dos fundos de identidade: as do marca.toml, ou a barra escurecendo (como na 0.7.7)."""
        light = self.light()
        return self.gradiente or [
            str(light.realce_texto),
            str(light.barra),
            mix(str(light.barra), str(light.foco), 0.5),
        ]


def _complete_light(p: Palette) -> Palette:
    if not p.barra or not p.destaque:
        raise BrandError("[cores.claro] precisa de 'barra' e 'destaque'.")
    org = p.organizacao or p.destaque
    bar_text = p.barra_texto or text_on(p.barra)
    button = p.botao or org
    return Palette(
        barra=p.barra,
        barra_borda=p.barra_borda or org,
        barra_texto=bar_text,
        barra_suave=p.barra_suave or mix(bar_text, p.barra, 0.78),
        selecao_fundo=p.selecao_fundo or bar_text,
        selecao_texto=p.selecao_texto or p.barra,
        realce=p.realce or mix(org, WHITE, 0.7),
        realce_texto=p.realce_texto or p.barra,
        botao=button,
        botao_hover=p.botao_hover or mix(button, "#000000", 0.86),
        botao_texto=p.botao_texto or text_on(button),
        organizacao=org,
        destaque=p.destaque,
        destaque_hover=p.destaque_hover or mix(p.destaque, "#000000", 0.88),
        destaque_fraco=p.destaque_fraco or mix(p.destaque, WHITE, 0.1),
        destaque_texto=p.destaque_texto or text_on(p.destaque),
        foco=p.foco or p.destaque,
        series=p.series,
        **_neutrals(p, "claro"),
    )


def _readable(text: str, surface: str, start: float, backgrounds: list[str]) -> str:
    """Mistura de texto com superfície o mais suave possível que ainda lê bem (4,6:1) em todos os fundos."""
    t = start
    while t < 1:
        color = mix(text, surface, t)
        if min(contrast(color, bg) for bg in backgrounds) >= 4.6:
            return color
        t += 0.02
    return text


def _neutrals(p: Palette, theme: str) -> dict[str, str]:
    """Fundo, superfície, bordas e texto da marca, com os tons intermediários que o tema usa."""
    given = [p.fundo, p.superficie, p.bordas, p.texto]
    if not any(given):
        return {}
    if not all(given):
        raise BrandError(f"[cores.{theme}] neutros: informe fundo, superficie, bordas e texto juntos.")
    bg, surface, border, text = (str(c) for c in given)
    surface_2 = mix(surface, bg, 0.5)
    surface_3 = mix(border, surface, 0.45)
    backgrounds = [bg, surface, surface_2, surface_3]
    return {
        "fundo": bg, "superficie": surface, "bordas": border, "texto": text,
        "superficie_2": surface_2, "superficie_3": surface_3, "tela": surface_2,
        "tela_ponto": mix(border, text, 0.9), "bordas_fortes": mix(border, text, 0.82),
        "texto_2": _readable(text, surface, 0.72, backgrounds), "texto_3": _readable(text, surface, 0.6, backgrounds),
    }  # fmt: skip


def _complete_dark(p: Palette | None, light: Palette) -> Palette:
    base = DARK_BAR.model_copy(update={"realce": light.realce, "realce_texto": light.realce_texto})
    if p is None:
        return base
    given = p.model_dump(exclude_none=True)
    merged = Palette(**{**base.model_dump(exclude_none=True), **given})
    button = merged.botao or base.botao
    updates: dict[str, object] = {}
    if "botao" in given and "botao_texto" not in given:
        updates["botao_texto"] = text_on(str(button))
    if "botao" in given and "botao_hover" not in given:
        updates["botao_hover"] = mix(str(button), WHITE, 0.85)
    if "barra" in given and "barra_texto" not in given:
        updates["barra_texto"] = text_on(str(merged.barra))
    if "barra" in given and "barra_suave" not in given:
        updates["barra_suave"] = mix(
            str(updates.get("barra_texto", merged.barra_texto)), str(merged.barra), 0.78
        )
    if merged.destaque:
        updates |= {
            "destaque_hover": merged.destaque_hover or mix(merged.destaque, WHITE, 0.85),
            "destaque_fraco": merged.destaque_fraco
            or mix(merged.destaque, merged.superficie or "#282a36", 0.3),
            "destaque_texto": merged.destaque_texto or text_on(merged.destaque),
            "foco": merged.foco or merged.destaque,
        }
    return merged.model_copy(update={**updates, **_neutrals(merged, "escuro")})


# ------------------------------------------------------------------ leitura e conferência


def load(brand_id: str) -> Brand:
    folder = MARCAS_DIR / brand_id
    toml = folder / "marca.toml"
    if not toml.is_file():
        known = ", ".join(available()) or "nenhuma"
        raise BrandError(f"Marca '{brand_id}' não encontrada em {MARCAS_DIR}. Marcas disponíveis: {known}.")
    try:
        data = tomllib.loads(toml.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise BrandError(f"{toml}: TOML inválido: {exc}") from exc
    colors = data.pop("cores", {})
    try:
        return Brand(id=brand_id, claro=colors.get("claro", {}), escuro=colors.get("escuro"), **data)
    except ValueError as exc:
        raise BrandError(f"{toml}: {exc}") from exc


def available() -> list[str]:
    if not MARCAS_DIR.is_dir():
        return []
    return sorted(p.name for p in MARCAS_DIR.iterdir() if (p / "marca.toml").is_file())


_PAIRS = (
    ("barra_texto", "barra", "texto da barra"),
    ("destaque_texto", "destaque", "texto sobre o destaque"),
    ("botao_texto", "botao", "texto do botão principal"),
    ("selecao_texto", "selecao_fundo", "aba escolhida na barra"),
)
_NEUTRAL_TEXT = (("texto", "texto"), ("texto_2", "texto secundário"), ("texto_3", "texto discreto"))


def _low(a: str | None, b: str | None, minimum: float) -> bool:
    return bool(a and b) and contrast(str(a), str(b)) < minimum


def _check_files(brand: Brand) -> list[str]:
    errors = [f"falta o arquivo {name}" for name in FILES if not (brand.dir / name).is_file()]
    files = font_files(brand)
    for font in sorted({brand.fonte_texto, brand.title_font, brand.fonte_codigo}):
        if font not in FONTS and font not in files.values():
            errors.append(f"a fonte '{font}' não vem com o programa: coloque {_slug(font)}*.woff2 em fontes/")
    return errors


def _check_theme(theme: str, p: Palette) -> tuple[list[str], list[str]]:
    errors = [
        f"{label} no tema {theme}: contraste {contrast(getattr(p, fg), getattr(p, bg)):.1f}:1, mínimo 4,5:1 "
        f"({getattr(p, fg)} sobre {getattr(p, bg)})"
        for fg, bg, label in _PAIRS
        if _low(getattr(p, fg), getattr(p, bg), 4.5)
    ]
    if p.texto:
        errors += [
            f"{label} sobre {bg} no tema {theme}: contraste {contrast(getattr(p, fg), getattr(p, bg)):.1f}:1, mínimo 4,5:1"
            for fg, label in _NEUTRAL_TEXT
            for bg in ("fundo", "superficie", "superficie_3")
            if _low(getattr(p, fg), getattr(p, bg), 4.5)
        ]
    surface = p.superficie or SURFACE[theme]
    warnings = [
        f"série {i} no tema {theme}: contraste {contrast(c, surface):.1f}:1 com o fundo ({c})"
        for i, c in enumerate(p.series or [], start=1)
        if _low(c, surface, 3)
    ]
    return errors, warnings


def check(brand: Brand) -> list[str]:
    """Confere o pacote. Levanta ``BrandError`` com todos os erros; devolve os avisos."""
    errors = _check_files(brand)
    warnings: list[str] = []
    try:
        themes = {"claro": brand.light(), "escuro": brand.dark()}
    except BrandError as exc:
        raise BrandError(f"Marca '{brand.id}': {exc}") from exc
    for theme, palette in themes.items():
        theme_errors, theme_warnings = _check_theme(theme, palette)
        errors += theme_errors
        warnings += theme_warnings
    text = str(themes["claro"].barra_texto)
    errors += [
        f"gradiente: o texto {text} sobre {c} tem contraste {contrast(text, c):.1f}:1, mínimo 4,5:1"
        for c in brand.gradiente
        if _low(text, c, 4.5)
    ]
    if errors:
        raise BrandError(f"Marca '{brand.id}':\n- " + "\n- ".join(errors))
    return warnings


def active_id() -> str:
    env = os.environ.get("PRODATA_MARCA", "").strip()
    if env:
        return env
    if ACTIVE_FILE.is_file():
        return ACTIVE_FILE.read_text(encoding="utf-8").strip() or DEFAULT
    return DEFAULT


@cache
def marca() -> Brand:
    """A marca ativa, lida uma vez por processo."""
    return load(active_id())


# ------------------------------------------------------------------ CSS


_VARS = {
    "barra": "--marca-barra", "barra_borda": "--marca-barra-borda", "barra_texto": "--marca-barra-texto",
    "barra_suave": "--marca-barra-suave", "selecao_fundo": "--marca-selecao-fundo", "selecao_texto": "--marca-selecao-texto",
    "realce": "--marca-realce", "realce_texto": "--marca-realce-texto", "botao": "--marca-botao",
    "botao_hover": "--marca-botao-hover", "botao_texto": "--marca-botao-texto", "organizacao": "--marca-org",
    "destaque": "--accent", "destaque_hover": "--accent-hover", "destaque_fraco": "--accent-weak",
    "destaque_texto": "--accent-text", "foco": "--focus",
    "fundo": "--bg", "superficie": "--surface", "superficie_2": "--surface-2", "superficie_3": "--surface-3",
    "tela": "--canvas", "tela_ponto": "--canvas-dot", "bordas": "--border", "bordas_fortes": "--border-strong",
    "texto": "--text", "texto_2": "--text-2", "texto_3": "--text-3",
}  # fmt: skip


def _slug(family: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")


# Faixas de caracteres dos arquivos divididos (…-latin-… e …-latin-ext-…), como em fonts.css.
_LATIN = "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2212"
_LATIN_EXT = "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1E00-1EFF, U+20A0-20C0"


def _range(file_name: str) -> str:
    if "latin-ext" in file_name:
        return f" unicode-range: {_LATIN_EXT};"
    return f" unicode-range: {_LATIN};" if "latin" in file_name else ""


def font_files(brand: Brand) -> dict[str, str]:
    """Arquivos .woff2 da marca e a família de cada um, pelo começo do nome (manrope-*.woff2 → Manrope)."""
    folder = brand.dir / "fontes"
    if not folder.is_dir():
        return {}
    families = {brand.fonte_texto, brand.title_font, brand.fonte_codigo} - set(FONTS)
    out = {}
    for file in sorted(folder.glob("*.woff2")):
        family = next((f for f in families if file.stem.lower().startswith(_slug(f))), None)
        if family:
            out[file.name] = family
    return out


def _declarations(p: Palette, font: str | None = None, action: bool = False) -> str:
    lines = [f"  {var}: {getattr(p, key)};" for key, var in _VARS.items() if getattr(p, key)]
    lines += [f"  --series-{i}: {c};" for i, c in enumerate(p.series or [], start=1)]
    if (
        action
    ):  # tema escuro: os botões de ação são o botão principal da marca (no claro, o destaque já faz isso)
        lines += [
            f"  --action: {p.botao};",
            f"  --action-hover: {p.botao_hover};",
            f"  --action-text: {p.botao_texto};",
        ]
    if font:
        lines.insert(0, f"  --font: '{font}', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;")
    return "\n".join(lines)


def css(brand: Brand) -> str:
    """Variáveis da marca para os dois temas, com os mesmos seletores de tokens.css (carregado depois dele)."""
    dark = _declarations(brand.dark(), action=True)
    fonts = "".join(
        f"@font-face {{ font-family: '{family}'; src: url('/marca/fontes/{name}') format('woff2'); "
        f"font-weight: 200 800; font-display: swap;{_range(name)} }}\n"
        for name, family in font_files(brand).items()
    )
    return (
        f"/* Marca {brand.id} (spec 036): gerado de marcas/{brand.id}/marca.toml. */\n{fonts}"
        f":root {{\n{_declarations(brand.light(), brand.fonte_texto)}\n"
        f"  --mono: '{brand.fonte_codigo}', ui-monospace, 'Cascadia Code', Consolas, monospace;\n"
        f"  --font-title: '{brand.title_font}', var(--font);\n}}\n"
        f'@media (prefers-color-scheme: dark) {{\n  :root:not([data-theme="light"]) {{\n{dark}\n  }}\n}}\n'
        f':root[data-theme="dark"] {{\n{dark}\n}}\n'
    )
