"""Formato dos itens do dashboard (spec 014, RF-1410..RF-1413, RF-1440..RF-1442).

Declarativos como as ferramentas (constituição III): o painel Formato é gerado destes modelos.
O formato só muda a aparência; nunca exige executar o fluxo de novo.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from prodata.forms import ui
from prodata.nodes.base import describe_fields

CARD = "Cartão"
COLORS = "Cores"
LABELS = "Rótulos e legenda"
AXES = "Eixos"
TIP = "Dica"


def _color(value: str) -> str:
    """Só #rrggbb (ou vazio = padrão do tema): o valor vai para estilos da página."""
    value = value.strip().lower()
    if value and not (
        len(value) == 7 and value[0] == "#" and all(c in "0123456789abcdef" for c in value[1:])
    ):
        raise ValueError("Cor inválida: use o formato #rrggbb.")
    return value


Color = Annotated[str, AfterValidator(_color)]


def _color_map(value: dict[str, str]) -> dict[str, str]:
    return {k[:200]: _color(v) for k, v in list(value.items())[:50] if _color(v)}


def _label_map(value: dict[str, str]) -> dict[str, str]:
    """Nomes exibidos no lugar dos originais (texto puro, curto); vazio = manter o original."""
    return {k[:200]: v.strip()[:100] for k, v in list(value.items())[:200] if v.strip() and v.strip() != k}


FONTS = {"theme": "Do tema", "sans": "Sem serifa", "serif": "Com serifa", "mono": "Monoespaçada"}
FontName = Literal["theme", "sans", "serif", "mono"]


class _Format(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CardFormat(_Format):
    show_title: bool = Field(True, title="Mostrar título")
    title: str = Field(
        "",
        title="Título",
        max_length=200,
        json_schema_extra=ui(placeholder="Igual ao da caixa no fluxo", show_if={"show_title": [True]}),
    )
    title_size: int = Field(
        14, ge=10, le=32, title="Tamanho do título", json_schema_extra=ui(show_if={"show_title": [True]})
    )
    title_align: Literal["left", "center"] = Field(
        "left",
        title="Alinhamento do título",
        json_schema_extra=ui(widget="segmented", labels={"left": "Esquerda", "center": "Centro"}),
    )
    # Fontes (spec 042, RF-4259)
    title_bold: bool = Field(
        True, title="Título em negrito", json_schema_extra=ui(show_if={"show_title": [True]})
    )
    title_italic: bool = Field(
        False, title="Título em itálico", json_schema_extra=ui(show_if={"show_title": [True]})
    )
    title_color: Color = Field(
        "", title="Cor do título", json_schema_extra=ui(widget="color", show_if={"show_title": [True]})
    )
    show_subtitle: bool = Field(True, title="Mostrar subtítulo")
    subtitle: str = Field(
        "",
        title="Subtítulo",
        max_length=200,
        json_schema_extra=ui(
            placeholder="Automático (o que o visual mostra)", show_if={"show_subtitle": [True]}
        ),
    )
    subtitle_size: int = Field(
        12, ge=9, le=24, title="Tamanho do subtítulo", json_schema_extra=ui(show_if={"show_subtitle": [True]})
    )
    subtitle_bold: bool = Field(
        False, title="Subtítulo em negrito", json_schema_extra=ui(show_if={"show_subtitle": [True]})
    )
    subtitle_italic: bool = Field(
        False, title="Subtítulo em itálico", json_schema_extra=ui(show_if={"show_subtitle": [True]})
    )
    subtitle_color: Color = Field(
        "", title="Cor do subtítulo", json_schema_extra=ui(widget="color", show_if={"show_subtitle": [True]})
    )
    font: FontName = Field("theme", title="Fonte do cartão", json_schema_extra=ui(group=CARD, labels=FONTS))
    background: Color = Field("", title="Fundo", json_schema_extra=ui(widget="color", group=CARD))
    border: bool = Field(True, title="Borda", json_schema_extra=ui(group=CARD))
    border_color: Color = Field(
        "", title="Cor da borda", json_schema_extra=ui(widget="color", group=CARD, show_if={"border": [True]})
    )
    radius: int = Field(10, ge=0, le=32, title="Cantos arredondados", json_schema_extra=ui(group=CARD))
    shadow: bool = Field(False, title="Sombra", json_schema_extra=ui(group=CARD))


# Paletas prontas (spec 042, RF-4234): as cores ficam em web/js/dash_look.js, que também vai no HTML exportado.
PALETTE_LABELS = {
    "brand": "Marca",
    "alt": "Alternativa",
    "okabe_ito": "Okabe-Ito (daltonismo)",
    "tableau10": "Tableau 10",
    "set2": "Set2 (ColorBrewer)",
    "viridis": "Viridis",
    "blues": "Tons de azul",
    "grays": "Tons de cinza",
    "personal": "Personalizada",
}
PaletteName = Literal["brand", "alt", "okabe_ito", "tableau10", "set2", "viridis", "blues", "grays"]
_OWN = {"page": "Paleta do dashboard", **PALETTE_LABELS, "single": "Uma cor só"}


class ChartFormat(CardFormat):
    # "page" (padrão) segue a paleta geral do dashboard (RF-4238); qualquer outra é a paleta própria do visual.
    palette: Literal[
        "page",
        "brand",
        "alt",
        "okabe_ito",
        "tableau10",
        "set2",
        "viridis",
        "blues",
        "grays",
        "personal",
        "single",
        "custom",
    ] = Field(
        "page",
        title="Cores",
        json_schema_extra=ui(
            widget="palette", group=COLORS, labels={**_OWN, "custom": "Uma cor por categoria"}
        ),
    )
    other_palette: Literal[
        "page",
        "brand",
        "alt",
        "okabe_ito",
        "tableau10",
        "set2",
        "viridis",
        "blues",
        "grays",
        "personal",
        "single",
    ] = Field(
        "page",
        title="Demais categorias",
        description="Cor do que não tem cor própria na lista abaixo.",
        json_schema_extra=ui(widget="palette", group=COLORS, show_if={"palette": ["custom"]}, labels=_OWN),
    )
    color: Color = Field(
        "",
        title="Cor única",
        json_schema_extra=ui(widget="color", group=COLORS, show_if={"palette": ["single", "custom"]}),
    )
    category_colors: Annotated[dict[str, str], AfterValidator(_color_map)] = Field(
        default_factory=dict,
        title="Cor de cada categoria",
        description="Mude uma cor para destacar só aquela categoria.",
        json_schema_extra=ui(widget="category_colors", group=COLORS),
    )
    data_labels: Literal["none", "max", "max_min", "all"] = Field(
        "max",
        title="Rótulos de dados",
        description="Números em destaque no gráfico. Com Todos, os que não cabem são omitidos para não se sobrepor;"
        " todos aparecem ao passar o mouse.",
        json_schema_extra=ui(
            group=LABELS,
            labels={"none": "Nenhum", "max": "Maior valor", "max_min": "Maior e menor", "all": "Todos"},
        ),
    )
    labels_bold: bool = Field(True, title="Rótulos em negrito", json_schema_extra=ui(group=LABELS))
    labels_color: Color = Field(
        "", title="Cor dos rótulos de dados", json_schema_extra=ui(widget="color", group=LABELS)
    )
    label_format: Literal["compact", "full"] = Field(
        "compact",
        title="Formato dos números",
        json_schema_extra=ui(
            group=LABELS, labels={"compact": "Compacto (1,2 mi)", "full": "Completo (1.234.567)"}
        ),
    )
    decimals: int = Field(1, ge=0, le=4, title="Casas decimais", json_schema_extra=ui(group=LABELS))
    prefix: str = Field(
        "", max_length=10, title="Prefixo", json_schema_extra=ui(group=LABELS, placeholder="R$ ")
    )
    suffix: str = Field(
        "", max_length=10, title="Sufixo", json_schema_extra=ui(group=LABELS, placeholder="%")
    )
    animate: bool = Field(
        True,
        title="Animar na linha do tempo",
        description="Desligado, os valores mudam de uma vez.",
        json_schema_extra=ui(group=LABELS),
    )
    show_legend: bool = Field(True, title="Mostrar legenda", json_schema_extra=ui(group=LABELS))
    legend_position: Literal["top", "bottom"] = Field(
        "top",
        title="Posição da legenda",
        json_schema_extra=ui(
            widget="segmented",
            group=LABELS,
            labels={"top": "Acima", "bottom": "Abaixo"},
            show_if={"show_legend": [True]},
        ),
    )
    labels: Annotated[dict[str, str], AfterValidator(_label_map)] = Field(
        default_factory=dict,
        title="Nomes na legenda e nas categorias",
        description="Troque o texto exibido de cada série, categoria ou conjunto (o dado não muda).",
        json_schema_extra=ui(widget="rename_labels", group=LABELS),
    )
    show_y_values: bool = Field(True, title="Valores do eixo Y", json_schema_extra=ui(group=AXES))
    axis_text_color: Color = Field(
        "", title="Cor dos textos dos eixos", json_schema_extra=ui(widget="color", group=AXES)
    )
    show_x_labels: bool = Field(True, title="Rótulos do eixo X", json_schema_extra=ui(group=AXES))
    grid: bool = Field(True, title="Linhas de grade", json_schema_extra=ui(group=AXES))
    # Spec 042 (RF-4256, RF-4257): desenho da grade e escala do eixo Y.
    grid_style: Literal["solid", "dashed", "dotted"] = Field(
        "solid",
        title="Estilo da grade",
        json_schema_extra=ui(
            widget="segmented",
            group=AXES,
            labels={"solid": "Contínua", "dashed": "Tracejada", "dotted": "Pontilhada"},
            show_if={"grid": [True]},
        ),
    )
    grid_color: Color = Field(
        "", title="Cor da grade", json_schema_extra=ui(widget="color", group=AXES, show_if={"grid": [True]})
    )
    grid_opacity: int = Field(
        100,
        ge=10,
        le=100,
        title="Opacidade da grade (%)",
        json_schema_extra=ui(group=AXES, show_if={"grid": [True]}),
    )
    ref_paint: bool = Field(
        True,
        title="Pintar acima e abaixo da linha de referência",
        description="A linha de referência é ligada no Configurar da caixa Chart.",
        json_schema_extra=ui(group=AXES),
    )
    ref_above: Color = Field(
        "", title="Cor acima", json_schema_extra=ui(widget="color", group=AXES, show_if={"ref_paint": [True]})
    )
    ref_below: Color = Field(
        "",
        title="Cor abaixo",
        json_schema_extra=ui(widget="color", group=AXES, show_if={"ref_paint": [True]}),
    )
    y_scale: Literal["linear", "log"] = Field(
        "linear",
        title="Escala do eixo Y",
        description="Logarítmica: cada marca vale 10 vezes a anterior. Zero e negativos ficam fora da escala; "
        "empilhados, 100% e rosca não usam.",
        json_schema_extra=ui(
            widget="segmented", group=AXES, labels={"linear": "Linear", "log": "Logarítmica"}
        ),
    )
    x_title: str = Field("", max_length=80, title="Título do eixo X", json_schema_extra=ui(group=AXES))
    y_title: str = Field("", max_length=80, title="Título do eixo Y", json_schema_extra=ui(group=AXES))
    y_min: float | None = Field(
        None, title="Mínimo do eixo Y", json_schema_extra=ui(group=AXES, widget="optional_number")
    )
    y_max: float | None = Field(
        None, title="Máximo do eixo Y", json_schema_extra=ui(group=AXES, widget="optional_number")
    )
    # Dica (spec 041, RF-4140..4143): o que aparece ao passar o mouse. As colunas extras ficam na caixa do gráfico,
    # que as agrega junto com o valor; aqui só se escolhem.
    tip_label: bool = Field(True, title="Categoria na dica", json_schema_extra=ui(group=TIP))
    tip_value: bool = Field(True, title="Valor na dica", json_schema_extra=ui(group=TIP))
    tip_percent: bool = Field(
        False,
        title="% do total na dica",
        description="Na rosca, o % aparece sempre.",
        json_schema_extra=ui(group=TIP),
    )
    tip_columns: list[str] = Field(
        default_factory=list, title="Colunas extras", json_schema_extra=ui(widget="tip_columns", group=TIP)
    )
    tip_text: str = Field(
        "",
        max_length=300,
        title="Texto da dica",
        description="Opcional: escreva a dica com os campos entre chaves. Vazio usa as opções acima.",
        json_schema_extra=ui(widget="tip_text", group=TIP, placeholder="Receita de {categoria}: {valor}"),
    )


RULES = "Cores por faixa"
_OPS = {
    "lt": "menor que",
    "le": "menor ou igual a",
    "gt": "maior que",
    "ge": "maior ou igual a",
    "eq": "igual a",
}
_STATUS = {"good": "Bom (verde)", "warning": "Atenção (amarelo)", "critical": "Crítico (vermelho)"}


class ValueRule(_Format):
    """Formatação condicional (RF-1414): cor de status com ícone, nunca só a cor."""

    op: Literal["lt", "le", "gt", "ge", "eq"] = Field(
        "lt", title="Quando o valor for", json_schema_extra=ui(labels=_OPS)
    )
    value: float = Field(0, title="Valor")
    status: Literal["good", "warning", "critical"] = Field(
        "critical", title="Marcar como", json_schema_extra=ui(labels=_STATUS)
    )


class ColumnRule(ValueRule):
    column: str = Field("", title="Coluna", json_schema_extra=ui(widget="column"))


class KpiFormat(CardFormat):
    value_size: int = Field(30, ge=16, le=96, title="Tamanho do número")
    value_color: Color = Field("", title="Cor do número", json_schema_extra=ui(widget="color"))
    align: Literal["left", "center"] = Field(
        "left",
        title="Alinhamento",
        json_schema_extra=ui(widget="segmented", labels={"left": "Esquerda", "center": "Centro"}),
    )
    show_footer: bool = Field(True, title="Mostrar rodapé (métrica e linhas)")
    value_rules: list[ValueRule] = Field(
        default_factory=list,
        title="Regras",
        description="A primeira regra que valer marca o indicador.",
        json_schema_extra=ui(group=RULES),
    )


class TableFormat(CardFormat):
    zebra: bool = Field(True, title="Linhas alternadas")
    compact: bool = Field(False, title="Linhas compactas")
    rules: list[ColumnRule] = Field(
        default_factory=list,
        title="Regras",
        description="Pinta o fundo da célula; a primeira regra que valer para a coluna é usada.",
        json_schema_extra=ui(group=RULES),
    )


class VisualFormat(ChartFormat, KpiFormat, TableFormat):
    """Validação no arquivo: um visual pode ser gráfico, KPI ou tabela."""


class TextFormat(_Format):
    size: int = Field(16, ge=8, le=96, title="Tamanho")
    font: FontName = Field("theme", title="Fonte", json_schema_extra=ui(labels=FONTS))
    bold: bool = Field(False, title="Negrito")
    italic: bool = Field(False, title="Itálico")
    underline: bool = Field(False, title="Sublinhado")
    color: Color = Field("", title="Cor", json_schema_extra=ui(widget="color"))
    align: Literal["left", "center", "right"] = Field(
        "left",
        title="Alinhamento",
        json_schema_extra=ui(
            widget="segmented", labels={"left": "Esquerda", "center": "Centro", "right": "Direita"}
        ),
    )
    vertical: Literal["top", "middle", "bottom"] = Field(
        "top",
        title="Posição vertical",
        json_schema_extra=ui(widget="segmented", labels={"top": "Topo", "middle": "Meio", "bottom": "Base"}),
    )
    background: Color = Field("", title="Fundo", json_schema_extra=ui(widget="color"))


class ImageFormat(_Format):
    fit: Literal["contain", "cover", "fill"] = Field(
        "contain",
        title="Encaixe",
        json_schema_extra=ui(
            labels={"contain": "Inteira, sem cortar", "cover": "Preencher (corta)", "fill": "Esticar"}
        ),
    )
    opacity: int = Field(100, ge=10, le=100, title="Opacidade (%)")
    radius: int = Field(0, ge=0, le=64, title="Cantos arredondados")


class ShapeFormat(_Format):
    shape: Literal["rect", "line"] = Field(
        "rect", title="Forma", json_schema_extra=ui(labels={"rect": "Retângulo", "line": "Linha"})
    )
    fill: Color = Field(
        "", title="Preenchimento", json_schema_extra=ui(widget="color", show_if={"shape": ["rect"]})
    )
    opacity: int = Field(100, ge=5, le=100, title="Opacidade (%)")
    stroke: Color = Field("", title="Cor da borda/linha", json_schema_extra=ui(widget="color"))
    stroke_width: int = Field(1, ge=0, le=16, title="Espessura")
    radius: int = Field(
        12, ge=0, le=64, title="Cantos arredondados", json_schema_extra=ui(show_if={"shape": ["rect"]})
    )


FORMATS: dict[str, type[_Format]] = {
    "chart": ChartFormat,
    "kpi": KpiFormat,
    "table": TableFormat,
    "text": TextFormat,
    "image": ImageFormat,
    "shape": ShapeFormat,
}
VALIDATORS: dict[str, type[_Format]] = {
    "visual": VisualFormat,
    "text": TextFormat,
    "image": ImageFormat,
    "shape": ShapeFormat,
}


TEXT = "Texto"
# Layout do painel Formato (spec 042, RF-4260): aba, bloco com título, meia largura, ordem e widget de cada campo.
# Fica aqui, separado dos modelos, para os campos continuarem iguais no arquivo do fluxo.
_TEXT_FIELDS = (
    "font",
    "title_size",
    "title_align",
    "title_bold",
    "title_italic",
    "title_color",
    "subtitle_size",
    "subtitle_bold",
    "subtitle_italic",
    "subtitle_color",
    "labels_bold",
    "labels_color",
    "axis_text_color",
    "value_size",
    "value_color",
    "align",
)
LAYOUT: dict[str, dict[str, Any]] = {
    **{name: {"group": TEXT} for name in _TEXT_FIELDS},
    # Cartão
    "background": {"half": True, "order": 1},
    "border_color": {"half": True, "order": 2},
    "border": {"order": 3},
    "shadow": {"order": 4},
    "radius": {"widget": "slider", "order": 5},
    # Rótulos
    "label_format": {"half": True},
    "decimals": {"half": True},
    "prefix": {"half": True},
    "suffix": {"half": True},
    # Eixos, em blocos
    "show_y_values": {"sub": "Eixo Y", "order": 1},
    "y_scale": {"sub": "Eixo Y", "order": 2},
    "y_title": {"sub": "Eixo Y", "order": 3},
    "y_min": {"sub": "Eixo Y", "half": True, "order": 4},
    "y_max": {"sub": "Eixo Y", "half": True, "order": 5},
    "show_x_labels": {"sub": "Eixo X", "order": 10},
    "x_title": {"sub": "Eixo X", "order": 11},
    "grid": {"sub": "Grade", "order": 20},
    "grid_style": {"sub": "Grade", "order": 21},
    "grid_color": {"sub": "Grade", "half": True, "order": 22},
    "grid_opacity": {"sub": "Grade", "half": True, "widget": "slider", "order": 23},
    "ref_paint": {"sub": "Linha de referência", "wide": True, "order": 30},
    "ref_above": {"sub": "Linha de referência", "half": True, "order": 31},
    "ref_below": {"sub": "Linha de referência", "half": True, "order": 32},
}


def describe_formats() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for kind, model in FORMATS.items():
        fields = describe_fields(model)
        if kind in ("chart", "kpi", "table"):  # texto, imagem e forma continuam num formulário só
            for field in fields:
                for key, value in LAYOUT.get(field["name"], {}).items():
                    if value is None:
                        field.pop(key, None)
                    else:
                        field[key] = value
        out[kind] = fields
    return out


def clean_format(kind: str, data: dict[str, Any]) -> dict[str, Any]:
    """Valida e guarda só o que difere do padrão (arquivo de fluxo enxuto)."""
    model = VALIDATORS[kind]
    return model.model_validate(data).model_dump(mode="json", exclude_defaults=True)
