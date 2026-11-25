"""CNPJ da Receita: leiaute, descompactação segura e a fonte de pasta pronta (spec 049, RF-4954, RF-4955, CA-05).

- O leiaute é o publicado pela Receita ("Novo leiaute dos dados abertos do CNPJ"): nomes, tipos e o significado de
  cada coluna. Os arquivos da Receita vêm sem cabeçalho, separados por ponto e vírgula, em Latin-1.
- Cada ZIP é conferido antes de abrir: um arquivo só dentro, caminho sem ``..`` nem absoluto, proporção de
  compactação plausível e tamanho descompactado com limite. O conteúdo é gravado com nome fixo
  (``estabelecimentos_3.csv``), convertido para UTF-8 e com a linha de cabeçalho do leiaute. A integridade (CRC) é
  conferida enquanto descompacta; um arquivo com defeito não fica com o nome final.
- A quantidade de colunas é conferida na primeira linha: se a Receita mudou o leiaute, o cabeçalho sai com nomes
  genéricos (``coluna_1``...) e a fonte avisa, sem adivinhar (RF-4955).
- A leitura lê tudo como texto (zeros à esquerda preservados) e converte só o que o leiaute diz: datas ``AAAAMMDD``
  e o capital social.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from prodata.catalog.readers.receita import GROUP_NAMES
from prodata.errors import MemoryAskError

LAYOUT_PREFIX = "receita.cnpj/"
MAX_RATIO = 60  # o CSV da Receita fica umas 4 a 10 vezes maior que o ZIP; 60 vezes é bomba
MAX_UNZIPPED = 60 * 1024**3  # nenhum arquivo do CNPJ chega perto de 60 GB descompactado
CHUNK = 4 * 1024 * 1024
SIDE_FILE = "leiaute.json"


class ZipRefusedError(ValueError):
    """ZIP que não é aberto, com o motivo em palavras."""


@dataclass(frozen=True)
class Col:
    nome: str
    tipo: str  # texto, data, numero
    descricao: str


_AUX = (Col("codigo", "texto", "Código."), Col("descricao", "texto", "Descrição do código."))
LAYOUTS: dict[str, tuple[Col, ...]] = {
    "empresas": (
        Col("cnpj_basico", "texto", "Os 8 primeiros dígitos do CNPJ: identificam a empresa."),
        Col("razao_social", "texto", "Nome empresarial."),
        Col("natureza_juridica", "texto", "Código da natureza jurídica (tabela Naturezas jurídicas)."),
        Col(
            "qualificacao_responsavel",
            "texto",
            "Qualificação da pessoa responsável pela empresa (tabela Qualificações).",
        ),
        Col("capital_social", "numero", "Capital social da empresa, em reais."),
        Col(
            "porte_empresa", "texto", "Porte: 00 não informado, 01 microempresa, 03 pequeno porte, 05 demais."
        ),
        Col("ente_federativo_responsavel", "texto", "Para órgãos públicos: o ente federativo responsável."),
    ),
    "estabelecimentos": (
        Col("cnpj_basico", "texto", "Os 8 primeiros dígitos do CNPJ: identificam a empresa."),
        Col("cnpj_ordem", "texto", "Os 4 dígitos do estabelecimento (0001 costuma ser a matriz)."),
        Col("cnpj_dv", "texto", "Os 2 dígitos verificadores do CNPJ."),
        Col("identificador_matriz_filial", "texto", "1 matriz, 2 filial."),
        Col("nome_fantasia", "texto", "Nome fantasia do estabelecimento."),
        Col("situacao_cadastral", "texto", "01 nula, 02 ativa, 03 suspensa, 04 inapta, 08 baixada."),
        Col("data_situacao_cadastral", "data", "Data do evento da situação cadastral."),
        Col("motivo_situacao_cadastral", "texto", "Código do motivo da situação cadastral (tabela Motivos)."),
        Col("nome_cidade_exterior", "texto", "Nome da cidade, para estabelecimentos no exterior."),
        Col("pais", "texto", "Código do país, para estabelecimentos no exterior (tabela Países)."),
        Col("data_inicio_atividade", "data", "Data de início da atividade."),
        Col("cnae_fiscal_principal", "texto", "Código da atividade econômica principal (tabela CNAE)."),
        Col("cnae_fiscal_secundaria", "texto", "Códigos das atividades secundárias, separados por vírgula."),
        Col("tipo_logradouro", "texto", "Tipo do logradouro (rua, avenida...)."),
        Col("logradouro", "texto", "Nome do logradouro."),
        Col("numero", "texto", "Número do endereço (pode ser S/N)."),
        Col("complemento", "texto", "Complemento do endereço."),
        Col("bairro", "texto", "Bairro."),
        Col("cep", "texto", "CEP, com os 8 dígitos."),
        Col("uf", "texto", "Sigla da UF."),
        Col(
            "municipio",
            "texto",
            "Código do município no código da Receita (tabela Municípios), não o do IBGE.",
        ),
        Col("ddd_1", "texto", "DDD do telefone 1."),
        Col("telefone_1", "texto", "Telefone 1."),
        Col("ddd_2", "texto", "DDD do telefone 2."),
        Col("telefone_2", "texto", "Telefone 2."),
        Col("ddd_fax", "texto", "DDD do fax."),
        Col("fax", "texto", "Fax."),
        Col("correio_eletronico", "texto", "E-mail informado à Receita."),
        Col("situacao_especial", "texto", "Situação especial da empresa."),
        Col("data_situacao_especial", "data", "Data em que entrou na situação especial."),
    ),
    "socios": (
        Col("cnpj_basico", "texto", "Os 8 primeiros dígitos do CNPJ da empresa."),
        Col("identificador_socio", "texto", "1 pessoa jurídica, 2 pessoa física, 3 estrangeiro."),
        Col(
            "nome_socio_razao_social",
            "texto",
            "Nome do sócio pessoa física ou razão social da pessoa jurídica.",
        ),
        Col("cpf_cnpj_socio", "texto", "CPF (mascarado pela Receita) ou CNPJ do sócio."),
        Col("qualificacao_socio", "texto", "Código da qualificação do sócio (tabela Qualificações)."),
        Col("data_entrada_sociedade", "data", "Data de entrada na sociedade."),
        Col("pais", "texto", "Código do país, para sócio estrangeiro (tabela Países)."),
        Col("representante_legal", "texto", "CPF do representante legal (mascarado pela Receita)."),
        Col("nome_do_representante", "texto", "Nome do representante legal."),
        Col(
            "qualificacao_representante_legal",
            "texto",
            "Código da qualificação do representante (tabela Qualificações).",
        ),
        Col("faixa_etaria", "texto", "Faixa etária do sócio, de 0 (não se aplica) a 9 (mais de 80 anos)."),
    ),
    "simples": (
        Col("cnpj_basico", "texto", "Os 8 primeiros dígitos do CNPJ da empresa."),
        Col("opcao_pelo_simples", "texto", "S optante, N não optante, vazio sem informação."),
        Col("data_opcao_simples", "data", "Data da opção pelo Simples Nacional."),
        Col("data_exclusao_simples", "data", "Data da exclusão do Simples Nacional."),
        Col("opcao_mei", "texto", "S optante pelo MEI, N não optante."),
        Col("data_opcao_mei", "data", "Data da opção pelo MEI."),
        Col("data_exclusao_mei", "data", "Data da exclusão do MEI."),
    ),
    "cnaes": _AUX,
    "motivos": _AUX,
    "municipios": _AUX,
    "naturezas": _AUX,
    "paises": _AUX,
    "qualificacoes": _AUX,
}
SINGLE = {"simples", "cnaes", "motivos", "municipios", "naturezas", "paises", "qualificacoes"}


def fixed_name(group: str, index: int | None) -> str:
    """O nome fixo do CSV: ``estabelecimentos_3.csv``, ``cnaes.csv``."""
    return f"{group}.csv" if index is None or group in SINGLE else f"{group}_{index}.csv"


def source_id_for(month: str, group: str) -> str:
    """O código da fonte de pasta: ``cnpj_2026_11_estabelecimentos`` (o mesmo em qualquer computador)."""
    return f"cnpj_{month.replace('-', '_')}_{group}"


def pattern_for(group: str) -> str:
    return f"{group}.csv" if group in SINGLE else f"{group}_*.csv"


def dictionary(group: str) -> list[dict[str, str]]:
    return [{"nome": c.nome, "tipo": c.tipo, "descricao": c.descricao} for c in LAYOUTS.get(group, ())]


# ------------------------------------------------------------------ conferir e descompactar


def _check_member(info: zipfile.ZipInfo, archive: str) -> None:
    name = info.filename.replace("\\", "/")
    if name.startswith("/") or ":" in name.split("/")[0] or any(p == ".." for p in name.split("/")):
        raise ZipRefusedError(
            f"{archive} tem um caminho para fora da pasta ({info.filename}). O ZIP não foi aberto."
        )
    if info.file_size > MAX_UNZIPPED:
        raise ZipRefusedError(
            f"{archive} diz ter {info.file_size} bytes descompactado: grande demais, não foi aberto."
        )
    if info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
        raise ZipRefusedError(
            f"{archive} descompacta {info.file_size // info.compress_size} vezes: parece uma bomba de ZIP."
        )


def inspect_zip(path: Path) -> zipfile.ZipInfo:
    """Confere o ZIP sem descompactar: um arquivo só dentro, com caminho e tamanhos plausíveis."""
    try:
        with zipfile.ZipFile(path) as archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
            for member in archive.infolist():
                _check_member(member, path.name)
    except zipfile.BadZipFile:
        raise ZipRefusedError(
            f"{path.name} não é um ZIP válido (o download pode ter vindo com defeito)."
        ) from None
    if len(members) != 1:
        raise ZipRefusedError(
            f"{path.name} tem {len(members)} arquivos dentro; a Receita publica um por ZIP."
        )
    return members[0]


def _header(first_line: str, group: str) -> tuple[list[str], str]:
    """Os nomes do cabeçalho e um aviso quando a quantidade de colunas não bate com o leiaute (RF-4955)."""
    layout = LAYOUTS[group]
    found = len(next(csv.reader([first_line], delimiter=";", quotechar='"'), []))
    if found == len(layout):
        return [c.nome for c in layout], ""
    names = [f"coluna_{i}" for i in range(1, found + 1)]
    return names, (f"A Receita mudou o leiaute de {GROUP_NAMES[group]}: {found} colunas, esperadas {len(layout)}. "
                   "As colunas vêm com nomes genéricos (coluna_1, coluna_2...), sem adivinhar.")  # fmt: skip


def extract(zip_path: Path, group: str, index: int | None, free: int | None = None) -> tuple[Path, str]:
    """Descompacta o único arquivo do ZIP para o nome fixo, em UTF-8 e com cabeçalho. Devolve o CSV e o aviso."""
    member = inspect_zip(zip_path)
    if free is not None and member.file_size * 1.05 > free:
        raise OSError(28, f"faltam {member.file_size - free} bytes para descompactar {zip_path.name}")
    final = zip_path.with_name(fixed_name(group, index))
    partial = final.with_name(final.name + ".parte")
    warning = ""
    written = 0
    try:
        with zipfile.ZipFile(zip_path) as archive, archive.open(member) as raw, partial.open("wb") as out:
            text = io.TextIOWrapper(raw, encoding="latin-1", newline="")
            first = text.readline()
            names, warning = _header(first.rstrip("\r\n"), group)
            out.write((";".join(names) + "\n").encode("utf-8"))
            out.write(first.encode("utf-8"))
            while chunk := text.read(CHUNK):
                written += len(chunk)
                if (
                    written > member.file_size
                ):  # o cabeçalho do ZIP mentiu o tamanho: para antes de encher o disco
                    raise ZipRefusedError(
                        f"{zip_path.name} tem mais conteúdo do que declara. Não foi aberto."
                    )
                out.write(chunk.encode("utf-8"))
    except zipfile.BadZipFile as exc:  # CRC que não confere: o arquivo veio com defeito
        partial.unlink(missing_ok=True)
        raise ZipRefusedError(f"{zip_path.name} veio com defeito ({exc}). Baixe de novo.") from None
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(final)
    return final, warning


def free_space(folder: Path) -> int:
    return shutil.disk_usage(folder).free


# ------------------------------------------------------------------ o lado do leiaute ao lado dos arquivos


def save_notes(folder: Path, notes: dict[str, str]) -> None:
    """Os avisos de leiaute de cada grupo, ao lado dos CSVs (a fonte de pasta mostra ao ler)."""
    if not any(notes.values()):
        return
    path = folder / SIDE_FILE
    with contextlib.suppress(OSError):
        current = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        current.update({k: v for k, v in notes.items() if v})
        path.write_text(json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ leitura com o leiaute


def group_of(layout: str) -> str | None:
    group = layout.removeprefix(LAYOUT_PREFIX) if layout.startswith(LAYOUT_PREFIX) else ""
    return group if group in LAYOUTS else None


# Filtro na leitura (RF-4957): os campos que cada tabela aceita e como aparecem na tela.
FILTERS: dict[str, dict[str, str]] = {
    "estabelecimentos": {"cnpj": "CNPJ", "uf": "UF", "municipio": "Município",
                         "cnae_fiscal_principal": "CNAE principal", "situacao_cadastral": "Situação cadastral"},
    "empresas": {"cnpj": "CNPJ"},
    "socios": {"cnpj": "CNPJ"},
    "simples": {"cnpj": "CNPJ"},
}  # fmt: skip
COMPANIES_OF = {"empresas", "socios", "simples"}  # "Só as empresas destes estabelecimentos"
SITUATIONS = {"01": "nula", "02": "ativa", "03": "suspensa", "04": "inapta", "08": "baixada"}
MAX_VALUES = 6000
MEMORY_SHARE = 4  # acima de 1/4 da memória, o Windows passa a usar o arquivo de paginação no disco
TEXT_IN_MEMORY = 1.6  # um CSV de texto ocupa umas 1,6 vezes o tamanho do arquivo na memória
SAMPLE_ROWS = 200_000


# ------------------------------------------------------------------ CNPJ em qualquer formato


def _dv_ok(cnpj14: str) -> bool:
    """Confere os dois dígitos verificadores do CNPJ (módulo 11)."""
    if len(cnpj14) != 14 or not cnpj14.isdigit() or len(set(cnpj14)) == 1:
        return False
    digits = [int(c) for c in cnpj14]
    for size in (12, 13):
        weights = list(range(size - 7, 1, -1)) + list(range(9, 1, -1))
        total = sum(d * w for d, w in zip(digits[:size], weights, strict=True))
        check = 0 if total % 11 < 2 else 11 - total % 11
        if digits[size] != check:
            return False
    return True


def format_cnpj(value: str) -> str:
    if len(value) == 14:
        return f"{value[:2]}.{value[2:5]}.{value[5:8]}/{value[8:12]}-{value[12:]}"
    return f"{value[:2]}.{value[2:5]}.{value[5:8]}"


def read_cnpj(text: str) -> dict[str, str] | None:
    """Uma linha colada pela pessoa, no formato da Receita: 14 dígitos (um estabelecimento, com os dígitos
    verificadores conferidos) ou 8 (a empresa inteira). Zeros à esquerda perdidos no Excel são completados."""
    raw = text.strip()
    digits = re.sub(r"\D", "", raw)
    if not digits or len(digits) > 14 or re.search(r"[A-Za-z]", raw):
        return None
    if len(digits) == 8 or (len(digits) < 8 and not _dv_ok(digits.zfill(14))):
        root = digits.zfill(8)
        return {"valor": root, "tipo": "empresa", "mostrado": format_cnpj(root)}
    full = digits.zfill(14)
    if not _dv_ok(full):
        return None
    return {"valor": full, "tipo": "estabelecimento", "mostrado": format_cnpj(full)}


def read_cnpj_list(text: str) -> dict[str, list[dict[str, str]]]:
    """A lista colada (um por linha, ou separados por vírgula ou ponto e vírgula), com como cada linha foi entendida."""
    valid: list[dict[str, str]] = []
    invalid: list[dict[str, str]] = []
    repeated: list[dict[str, str]] = []
    seen: set[str] = set()
    for piece in re.split(r"[\n,;]+", text or ""):
        if not piece.strip():
            continue
        found = read_cnpj(piece)
        if found is None:
            invalid.append({"entrada": piece.strip()[:40]})
        elif found["valor"] in seen:  # o mesmo CNPJ escrito de outro jeito: aparece como repetido, não some
            repeated.append({"entrada": piece.strip()[:40], **found})
        else:
            seen.add(found["valor"])
            valid.append({"entrada": piece.strip()[:40], **found})
    return {"validos": valid, "invalidos": invalid, "repetidos": repeated}


def check_filter(layout: str, filters: dict[str, list[str]], companies_of: str) -> None:
    """O filtro só usa campos que a tabela tem, com valores curtos; ``ValueError`` com o motivo."""
    group = group_of(layout) if layout else None
    if (filters or companies_of) and group is None:
        raise ValueError("O filtro na leitura vale só para as fontes do CNPJ da Receita.")
    allowed = FILTERS.get(group or "", {})
    for key, values in filters.items():
        if key not in allowed:
            raise ValueError(f"{GROUP_NAMES.get(group or '', group)} não filtra por {key}.")
        if len(values) > MAX_VALUES or any(
            not v or len(v) > 20 or not v.replace(" ", "").isalnum() for v in values
        ):
            raise ValueError(f"Valores inválidos no filtro de {allowed[key]}.")
        if key == "cnpj" and any(not v.isdigit() or len(v) not in (8, 14) for v in values):
            raise ValueError(
                "O filtro de CNPJ guarda só CNPJs de 14 dígitos ou raízes de 8 (a tela converte)."
            )
    if companies_of and group not in COMPANIES_OF:
        raise ValueError("Só as empresas destes estabelecimentos vale para Empresas, Sócios e Simples.")


def filter_words(layout: str, filters: dict[str, list[str]], companies_of_name: str = "") -> str:
    """O filtro em palavras, para a prévia, o Perfil e a caixa: "UF: SP, RJ · CNAE principal: 4721102"."""
    group = group_of(layout) or ""
    parts = []
    for key, values in filters.items():
        if not values:
            continue
        if key == "cnpj":
            shown = [format_cnpj(v) + ("" if len(v) == 14 else " (empresa)") for v in values[:5]]
        elif key == "situacao_cadastral":
            shown = [f"{v} ({SITUATIONS[v]})" if v in SITUATIONS else v for v in values[:5]]
        else:
            shown = values[:5]
        more = f" e mais {len(values) - 5}" if len(values) > 5 else ""
        parts.append(f"{FILTERS.get(group, {}).get(key, key)}: {', '.join(shown)}{more}")
    if companies_of_name:
        parts.append(f"só as empresas de {companies_of_name}")
    return " · ".join(parts)


def _apply(
    lazy: pl.LazyFrame, group: str, filters: dict[str, list[str]], companies: pl.Series | None
) -> pl.LazyFrame:
    for key, values in filters.items():
        if not values:
            continue
        if key == "cnpj":
            roots = [v for v in values if len(v) == 8]
            fulls = [v for v in values if len(v) == 14]
            if group == "estabelecimentos":
                whole = pl.concat_str(["cnpj_basico", "cnpj_ordem", "cnpj_dv"])
                lazy = lazy.filter(pl.col("cnpj_basico").is_in(roots) | whole.is_in(fulls))
            else:  # Empresas, Sócios e Simples não têm a filial: vale a raiz
                lazy = lazy.filter(pl.col("cnpj_basico").is_in(sorted({*roots, *(f[:8] for f in fulls)})))
        else:
            lazy = lazy.filter(pl.col(key).is_in(values))
    if companies is not None:
        lazy = lazy.filter(pl.col("cnpj_basico").is_in(companies))
    return lazy


def _scan(path: Path) -> pl.LazyFrame:
    return pl.scan_csv(path, separator=";", quote_char='"', infer_schema=False)


# ------------------------------------------------------------------ memória (RF-4957)


def memory_budget(memory: int) -> int:
    return memory // MEMORY_SHARE


def estimate(
    files: list[Path], layout: str, filters: dict[str, list[str]], companies: pl.Series | None
) -> int:
    """Quanto a leitura deve ocupar na memória: sem filtro, pelo tamanho dos arquivos; com filtro, por um trecho do
    primeiro arquivo lido de verdade, com a proporção de linhas que passam projetada para o total."""
    full = int(sum(p.stat().st_size for p in files) * TEXT_IN_MEMORY)
    if not files or (not any(filters.values()) and companies is None):
        return full
    sample = _scan(files[0]).head(SAMPLE_ROWS).collect()
    if not sample.height:
        return 0
    passed = _apply(sample.lazy(), group_of(layout) or "", filters, companies).collect().height
    return int(full * passed / sample.height)


def memory_question(estimated: int, memory: int, layout: str, read_so_far: bool = False) -> MemoryAskError:
    group = group_of(layout) or ""
    hint = ("Filtre mais (UF, município, CNAE, situação ou CNPJ)" if group == "estabelecimentos"
            else "Use Só as empresas destes estabelecimentos ou o filtro de CNPJ" if group in COMPANIES_OF
            else "Use um limite de linhas")  # fmt: skip
    what = ("O que já foi lido passou" if read_so_far
            else f"Esta leitura deve ocupar cerca de {_gb(estimated)}, mais")  # fmt: skip
    return MemoryAskError(
        f"{what} de 1/4 da memória deste computador ({_gb(memory)}). Acima disso o Windows usa o disco como memória e "
        f"tudo fica muito lento. {hint}, ou escolha Continuar assim mesmo.",
        estimated,
        memory,
    )


def _gb(n: int) -> str:
    return f"{n / 1024**3:.1f} GB".replace(".", ",")


def read_file(
    path: Path,
    layout: str,
    n_rows: int | None = None,
    filters: dict[str, list[str]] | None = None,
    companies: pl.Series | None = None,
) -> tuple[pl.DataFrame, list[str]]:
    """Lê um CSV do CNPJ preparado pelo programa: tudo como texto, com os tipos do leiaute nas colunas que batem.

    Com filtro, lê aos poucos (sem carregar o arquivo inteiro) e guarda só as linhas que passam.
    """
    group = group_of(layout)
    if group is None:
        raise ValueError(f"Leiaute desconhecido: {layout}")
    lazy = _scan(path)
    expected = [c.nome for c in LAYOUTS[group]]
    columns = lazy.collect_schema().names()
    if columns != expected:
        if any((filters or {}).values()) or companies is not None:
            raise ValueError(f"{path.name}: a Receita mudou o leiaute de {GROUP_NAMES[group]}, então o filtro na "
                             "leitura não pode ser aplicado. Confira os arquivos do mês.")  # fmt: skip
        frame = lazy.head(n_rows).collect() if n_rows else lazy.collect()
        return frame, [f"{path.name}: as colunas não batem com o leiaute de {GROUP_NAMES[group]} da Receita; "
                       "lidas como texto, com os nomes do arquivo."]  # fmt: skip
    lazy = _apply(lazy, group, filters or {}, companies)
    if n_rows:
        lazy = lazy.head(n_rows)
    frame = lazy.collect(engine="streaming")
    casts = []
    for col in LAYOUTS[group]:
        if col.tipo == "data":
            casts.append(pl.col(col.nome).replace({"0": None, "00000000": None, "": None})
                         .str.strptime(pl.Date, "%Y%m%d", strict=False).alias(col.nome))  # fmt: skip
        elif col.tipo == "numero":
            casts.append(pl.col(col.nome).str.replace_all(r"\.", "").str.replace(",", ".")
                         .cast(pl.Float64, strict=False).alias(col.nome))  # fmt: skip
    return (frame.with_columns(casts) if casts else frame), []


def companies_in(files: list[Path], filters: dict[str, list[str]]) -> pl.Series:
    """Os CNPJs básicos dos estabelecimentos que passam no filtro, lidos aos poucos (só a coluna que importa)."""
    found = [
        _apply(_scan(path), "estabelecimentos", filters, None).select("cnpj_basico").unique()
        .collect(engine="streaming")["cnpj_basico"]
        for path in files
    ]  # fmt: skip
    return pl.concat(found).unique() if found else pl.Series("cnpj_basico", [], dtype=pl.String)


def with_layout(extra: dict[str, Any], layout: str, folder: Path, notes: list[str]) -> dict[str, Any]:
    """O resultado da fonte de pasta do CNPJ: o dicionário e a citação (``fonte_publica``) e os avisos de leiaute."""
    info = layout_info(layout, folder)
    if info:
        extra["fonte_publica"] = {**info, "lido_em": extra.get("source_read_at")}
        notes = [info["aviso"], *notes] if info["aviso"] else notes
    if notes:
        extra["warnings"] = [*extra.get("warnings", []), *notes]
    return extra


def layout_info(layout: str, folder: Path) -> dict[str, Any] | None:
    """O que a caixa mostra no Perfil e na citação: o dicionário e o aviso de leiaute, se houver."""
    group = group_of(layout)
    if group is None:
        return None
    notes: dict[str, str] = {}
    with contextlib.suppress(OSError, ValueError):
        notes = json.loads((folder / SIDE_FILE).read_text(encoding="utf-8"))
    month = folder.name.removeprefix("CNPJ-")
    return {
        "id": "receita.cnpj/dados-abertos", "nome": f"CNPJ {month} · {GROUP_NAMES[group]}",
        "orgao": "Receita Federal do Brasil", "citacao": f"Receita Federal do Brasil, Dados Abertos do CNPJ ({month})",
        "licenca": "Dados abertos da Receita Federal: uso livre com citação da fonte.",
        "colunas": dictionary(group), "aviso": notes.get(group, ""),
    }  # fmt: skip


# ------------------------------------------------------------------ depois do download: descompactar e cadastrar


def finish(manager: Any, job: dict[str, Any], *, folders: Any, organization: Any) -> None:
    """Confere e descompacta cada ZIP e cadastra as fontes de pasta prontas, numa pasta da vista Dados (RF-4954).

    Roda na linha de execução do download. Disco cheio pausa (Continuar retoma daqui); ZIP com defeito volta a ser
    baixado no Continuar; ZIP recusado (caminho para fora, bomba) é apagado e o motivo fica no download.
    """
    dest = Path(job["destino"])
    notes: dict[str, str] = {}

    def update(**fields: Any) -> None:
        with manager._lock:
            job.update(fields)
            manager._save(job)

    update(estado="descompactando", motivo="")
    for part in job["partes"]:
        if part["estado"] == "pronto":
            continue
        zip_path = dest / part["arquivo"]
        with manager._lock:
            part["estado"] = "descompactando"
        update()
        try:
            _csv, warning = extract(zip_path, part["grupo"], part["indice"], free_space(dest))
        except ZipRefusedError as exc:
            zip_path.unlink(missing_ok=True)
            with manager._lock:  # Continuar baixa esta parte de novo, do zero
                part.update(estado="erro", baixado=0, tentativas=0)
            update(estado="erro", motivo=str(exc))
            return
        except OSError as exc:
            with manager._lock:
                part["estado"] = "baixado"
            if exc.errno == 28 or getattr(exc, "winerror", None) in (39, 112):
                update(
                    estado="pausado",
                    motivo=f"Falta espaço em {dest} para descompactar. Libere espaço e use Continuar.",
                )
            else:
                update(estado="erro", motivo=f"Não foi possível descompactar {part['arquivo']}: {exc}")
            return
        if warning:
            notes[part["grupo"]] = warning
        if not job.get("manter_zips"):
            zip_path.unlink(missing_ok=True)
        with manager._lock:
            part["estado"] = "pronto"
        update()
    save_notes(dest, notes)
    sources = register(job, folders=folders, organization=organization)
    update(estado="concluido", motivo="", fontes=sources, avisos=list(notes.values()))


def register(job: dict[str, Any], *, folders: Any, organization: Any) -> list[str]:
    """Uma fonte de pasta por grupo baixado, com o leiaute; todas na pasta "CNPJ AAAA-MM" da vista Dados."""
    from prodata.ingestion.folders import FolderSource
    from prodata.services.organization import SourceChanges

    month = job["mes"]
    groups = list(dict.fromkeys(p["grupo"] for p in job["partes"] if p["estado"] == "pronto"))
    existing = {s.id: s for s in folders.list()}
    keys: list[str] = []
    for group in groups:
        # Código previsível: no computador do colega, o mesmo mês baixado vira a mesma fonte, e o fluxo
        # compartilhado funciona sem trocar nada (RF-4972). Baixar de novo mantém o filtro que já havia.
        source_id = source_id_for(month, group)
        before = existing.get(source_id)
        source = FolderSource(
            id=source_id, name=f"CNPJ {month} · {GROUP_NAMES[group]}", folder=job["destino"], pattern=pattern_for(group),
            file_column="" if group in SINGLE else "arquivo", format="csv", delimiter=";", encoding="utf-8",
            has_header=True, layout=f"{LAYOUT_PREFIX}{group}",
            layout_filter=before.layout_filter if before else {},
            layout_companies_of=before.layout_companies_of if before else "",
        )  # fmt: skip
        saved = folders.save(source, source_id if before else None)
        keys.append(f"folder:{saved.id}")
    title = f"CNPJ {month}"
    org = organization.get()
    folder = next((f for f in org.folders if f.name == title), None)
    if folder is None:
        org = organization.add_folder(title, "verde")
        folder = next(f for f in org.folders if f.name == title)
    if keys:
        organization.change_sources(keys, SourceChanges(folder=folder.id))
    return keys


def lookup_values(folder: Path, table: str, query: str, limit: int = 30) -> dict[str, Any]:
    """Busca na tabela auxiliar baixada (municípios ou CNAE), sem acento e pelo código ou pelo nome."""
    import unicodedata

    path = folder / f"{table}.csv"
    if table not in ("municipios", "cnaes") or not path.is_file():
        return {"valores": [], "disponivel": False}

    def plain(text: str) -> str:
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()

    frame = pl.read_csv(path, separator=";", quote_char='"', infer_schema=False)
    if frame.columns != ["codigo", "descricao"]:
        return {"valores": [], "disponivel": False}
    wanted = plain(query.strip())
    rows = [r for r in frame.iter_rows() if not wanted or wanted in plain(f"{r[0]} {r[1] or ''}")]
    return {"valores": [{"codigo": c, "descricao": d or ""} for c, d in rows[:limit]], "disponivel": True,
            "total": len(rows)}  # fmt: skip
