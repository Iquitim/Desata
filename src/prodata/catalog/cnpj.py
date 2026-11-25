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
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from prodata.catalog.readers.receita import GROUP_NAMES

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


def read_file(path: Path, layout: str, n_rows: int | None = None) -> tuple[pl.DataFrame, list[str]]:
    """Lê um CSV do CNPJ preparado pelo programa: tudo como texto, com os tipos do leiaute nas colunas que batem."""
    group = group_of(layout)
    if group is None:
        raise ValueError(f"Leiaute desconhecido: {layout}")
    frame = pl.read_csv(path, separator=";", quote_char='"', infer_schema=False, n_rows=n_rows)
    expected = [c.nome for c in LAYOUTS[group]]
    if frame.columns != expected:
        return frame, [f"{path.name}: as colunas não batem com o leiaute de {GROUP_NAMES[group]} da Receita; "
                       "lidas como texto, com os nomes do arquivo."]  # fmt: skip
    casts = []
    for col in LAYOUTS[group]:
        if col.tipo == "data":
            casts.append(pl.col(col.nome).replace({"0": None, "00000000": None, "": None})
                         .str.strptime(pl.Date, "%Y%m%d", strict=False).alias(col.nome))  # fmt: skip
        elif col.tipo == "numero":
            casts.append(pl.col(col.nome).str.replace_all(r"\.", "").str.replace(",", ".")
                         .cast(pl.Float64, strict=False).alias(col.nome))  # fmt: skip
    return (frame.with_columns(casts) if casts else frame), []


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
    existing = {s.name.casefold(): s.id for s in folders.list()}
    keys: list[str] = []
    for group in groups:
        name = f"CNPJ {month} · {GROUP_NAMES[group]}"
        source = FolderSource(
            name=name, folder=job["destino"], pattern=pattern_for(group), file_column="" if group in SINGLE else "arquivo",
            format="csv", delimiter=";", encoding="utf-8", has_header=True, layout=f"{LAYOUT_PREFIX}{group}",
        )  # fmt: skip
        saved = folders.save(source, existing.get(name.casefold()))
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
