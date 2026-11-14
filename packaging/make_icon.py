"""Gera os ícones e as imagens do instalador a partir da marca ativa (spec 036): ícone, paleta e nome.

- ``packaging/prodata.ico``: ícone do executável e do instalador.
- ``packaging/wizard-*.bmp``: imagens das telas do instalador (Inno Setup), em três escalas.
- ``packaging/splash.png``: tela de abertura mostrada enquanto o programa carrega (spec 018).

O ícone vem de ``marcas/<id>/icone.png`` (e ``icone-escuro.png``, quando existe, para os fundos da cor da barra).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from prodata.brand import marca


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


SIZES = [16, 24, 32, 48, 64, 128, 256]
HERE = Path(__file__).resolve().parent
BRAND = marca()
SHIELD = BRAND.dir / "icone.png"
SHIELD_LIGHT = (
    BRAND.dir / "icone-escuro.png" if (BRAND.dir / "icone-escuro.png").is_file() else SHIELD
)  # fundo da barra
OUT = HERE / "prodata.ico"

_LIGHT = BRAND.light()
NAVY = _rgb(str(_LIGHT.barra))
NAVY_DEEP = _rgb(str(_LIGHT.realce_texto))
GOLD = _rgb(str(_LIGHT.organizacao))
SOFT = _rgb(str(_LIGHT.barra_suave))
BAR_TEXT = _rgb(str(_LIGHT.barra_texto))
WHITE = (255, 255, 255)

# Inno Setup: imagem lateral 164x314 e pequena 55x58 a 100%; 150% e 200% para telas de alta densidade.
SCALES = {100: 1.0, 150: 1.5, 200: 2.0}


def _background(w: int, h: int) -> Image.Image:
    """Fundo de identidade: o gradiente da marca em diagonal, ou a barra escurecendo para cima (como na 0.7.7)."""
    if not BRAND.gradiente:
        img = Image.new("RGB", (w, h), NAVY)
        for y in range(h):  # gradiente vertical simples, do tom escuro ao da barra
            t = y / max(1, h - 1)
            img.paste(
                tuple(round(NAVY_DEEP[i] + (NAVY[i] - NAVY_DEEP[i]) * t) for i in range(3)), (0, y, w, y + 1)
            )
        return img
    stops = [_rgb(c) for c in BRAND.gradiente]
    img = Image.new("RGB", (w, h))
    pixels = img.load()
    assert pixels is not None
    for y in range(h):
        for x in range(w):
            t = (x / max(1, w - 1)) * 0.7 + (y / max(1, h - 1)) * 0.3  # da esquerda em cima à direita embaixo
            pos = t * (len(stops) - 1)
            i = min(int(pos), len(stops) - 2)
            f = pos - i
            pixels[x, y] = tuple(round(stops[i][k] + (stops[i + 1][k] - stops[i][k]) * f) for k in range(3))
    return img


def _shield(path: Path, size: int) -> Image.Image:
    return Image.open(path).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


def wizard_image(scale: float) -> Image.Image:
    """Faixa lateral: fundo de identidade, ícone para fundo escuro e filete na cor da organização embaixo."""
    w, h = round(164 * scale), round(314 * scale)
    img = _background(w, h)
    shield = _shield(SHIELD_LIGHT, round(w * 0.72))
    img.paste(shield, ((w - shield.width) // 2, round(h * 0.18)), shield)
    img.paste(GOLD, (0, h - round(7 * scale), w, h))
    return img


def wizard_small_image(scale: float) -> Image.Image:
    """Canto superior direito das páginas do instalador: escudo oficial sobre branco."""
    w, h = round(55 * scale), round(58 * scale)
    img = Image.new("RGB", (w, h), WHITE)
    shield = _shield(SHIELD, round(min(w, h) * 0.92))
    img.paste(shield, ((w - shield.width) // 2, (h - shield.height) // 2), shield)
    return img


SPLASH_SIZE = (520, 300)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(name, size)
    except OSError:  # fora do Windows (CI): fonte padrão
        return ImageFont.load_default(size)


def _wrap(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, width: int
) -> list[str]:
    """Quebra o texto em linhas que cabem na largura: uma frase por linha quando cabe, senão palavra a palavra."""
    sentences = [s if s.endswith(".") else f"{s}." for s in text.rstrip(".").split(". ")]
    if len(sentences) > 1 and all(draw.textlength(s, font=font) <= width for s in sentences):
        return sentences
    lines: list[str] = []
    for word in text.split():
        candidate = f"{lines[-1]} {word}" if lines else word
        if lines and draw.textlength(candidate, font=font) <= width:
            lines[-1] = candidate
        else:
            lines.append(word)
    return lines


def splash_image(version: str) -> Image.Image:
    """Tela de abertura: fundo de identidade, ícone, nome, slogan e versão. O texto de andamento é escrito
    pelo próprio executável na faixa de baixo (``text_pos`` no prodata.spec)."""
    w, h = SPLASH_SIZE
    img = _background(w, h)
    shield = _shield(SHIELD_LIGHT, 132)
    img.paste(shield, (44, 62), shield)
    draw = ImageDraw.Draw(img)
    draw.text((200, 92), BRAND.nome, font=_font("segoeuib.ttf", 46), fill=BAR_TEXT)
    line = f"Versão {version} · {BRAND.organizacao}" if BRAND.organizacao else f"Versão {version}"
    if BRAND.slogan:
        font = _font("segoeui.ttf", 15)
        lines = _wrap(draw, BRAND.slogan, font, w - 203 - 24)
        for i, text in enumerate(lines):
            draw.text((203, 150 + i * 20), text, font=font, fill=BAR_TEXT)
        draw.text((203, 156 + len(lines) * 20), line, font=_font("segoeui.ttf", 13), fill=SOFT)
    else:
        draw.text((203, 152), line, font=_font("segoeui.ttf", 16), fill=SOFT)
    img.paste(GOLD, (0, h - 6, w, h))
    return img


def main() -> None:
    source = Image.open(SHIELD).convert("RGBA")
    images = [source.resize((s, s), Image.Resampling.LANCZOS) for s in SIZES]
    images[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print(f"Ícone gerado: {OUT}")
    for pct, scale in SCALES.items():
        wizard_image(scale).save(HERE / f"wizard-{pct}.bmp")
        wizard_small_image(scale).save(HERE / f"wizard-small-{pct}.bmp")
    print("Imagens do instalador geradas: wizard-*.bmp")
    from prodata import __version__

    splash_image(__version__).save(HERE / "splash.png")
    print("Tela de abertura gerada: splash.png")


if __name__ == "__main__":
    main()
