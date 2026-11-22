"""Linha de comando (spec 033): ``prodata run <fluxo>`` executa sem servidor e sem janela.

Feito para o Agendador do Windows: o código de saída diz se deu certo, e o relatório fica na pasta de dados.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from prodata import __version__
from prodata.api.deps import Services
from prodata.brand import marca
from prodata.config import Settings
from prodata.domain.execution import ExecutionReport
from prodata.domain.workflow import ID_PATTERN, Workflow
from prodata.errors import InvalidInputError, NotFoundError, ProdataError
from prodata.scheduling.service import SPACE_TARGET
from prodata.services.workflows import SUFFIX, load_from_file
from prodata.team.runtime import runner_for

OK, FAILED, REFUSED = 0, 1, 2
_STATUS = {
    "executed": "ok",
    "cached": "ok (cache)",
    "error": "ERRO",
    "skipped": "não executou",
    "disabled": "desativada",
}


def _services() -> Services:
    from prodata.main import build_services

    if getattr(sys, "frozen", False) and "PRODATA_STORAGE_DIR" not in os.environ:
        # O executável instalado usa a mesma pasta de dados do programa com janela.
        from prodata.desktop import user_data_dir

        os.environ["PRODATA_STORAGE_DIR"] = str(user_data_dir())
    return build_services(Settings())


def find_workflow(services: Services, name: str) -> Workflow:
    """Arquivo ``.prodata.json`` (caminho) ou fluxo da biblioteca (ID ou nome)."""
    as_path = Path(name)
    if name.lower().endswith(".json") or as_path.is_file():
        workflow, _ = load_from_file(str(as_path.resolve()))
        return workflow
    if re.fullmatch(ID_PATTERN, name) and services.workflows.exists(name):
        return services.workflows.get(name)
    matches = [s for s in services.workflows.list() if s.name.casefold() == name.casefold()]
    if len(matches) == 1:
        return services.workflows.get(matches[0].id)
    if len(matches) > 1:
        ids = ", ".join(m.id for m in matches)
        raise InvalidInputError(f"Há mais de um fluxo chamado '{name}'. Use o ID: {ids}")
    raise NotFoundError(
        f"Fluxo não encontrado: {name}. Use o caminho de um arquivo {SUFFIX}, ou veja os da biblioteca com 'prodata list'."
    )


def _save_report(folder: Path, workflow: Workflow, report: ExecutionReport) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%Hh%Mm%S")
    path = folder / f"{workflow.id}_{stamp}.json"
    path.write_text(report.model_dump_json(indent=1), encoding="utf-8")
    return path


def _print_report(workflow: Workflow, report: ExecutionReport, quiet: bool) -> int:
    failed = 0
    for node_id, result in report.node_results.items():
        node = workflow.node(node_id)
        failed += result.status == "error"
        if quiet and result.status != "error":
            continue
        label = node.label or node.type
        line = f"  [{_STATUS.get(result.status, result.status)}] {label}"
        if result.status in ("error", "skipped") and result.error:
            line += f": {result.error}"
        elif exported := result.extra.get("exported_path") or result.extra.get("exported_file"):
            line += f" -> {exported}"
        print(line)
        for warning in result.extra.get("warnings") or []:
            print(f"      aviso: {warning}")
    return failed


def _record(
    args: argparse.Namespace,
    started: datetime,
    status: str,
    name: str,
    message: str,
    report: ExecutionReport | None = None,
) -> None:
    """Agendamento (spec 044, RF-4434/4435): grava a execução no histórico, inclusive quando recusa."""
    schedule = getattr(args, "agendamento", None)
    if not schedule or not re.fullmatch(r"[a-f0-9]{8}", schedule):
        return
    from prodata.scheduling.store import RunRecord, ScheduleStore

    results = report.node_results.values() if report else []
    storage = Settings().storage_dir
    try:
        ScheduleStore(storage / "agendamentos.json", storage / "logs" / "agendamentos.jsonl").record(
            RunRecord(
                schedule_id=schedule,
                workflow=name,
                started_at=started,
                finished_at=datetime.now(),
                status=status,
                errors=sum(r.status == "error" for r in results),
                files=sum(
                    bool(r.extra.get("exported_path") or r.extra.get("exported_file")) for r in results
                ),
                message=message[:500],
            )
        )
    except OSError as exc:
        print(f"Histórico do agendamento não gravado: {exc}", file=sys.stderr)
        return
    if SPACE_TARGET.match(
        getattr(args, "fluxo", "") or ""
    ):  # o time vê a última execução (spec 047, RF-4753)
        try:
            _services().schedules.share_after_run(schedule)
        except (ProdataError, OSError, ValueError) as exc:
            print(f"Estado do agendamento não publicado no espaço: {exc}", file=sys.stderr)


def _space_official(
    services: Services, args: argparse.Namespace, space_id: str, workflow_id: str
) -> Workflow:
    """A versão oficial do fluxo do espaço, se confere; senão, recusa com o motivo (RF-4752). Um agendamento que outra
    pessoa assumiu não roda mais neste computador (RF-4753)."""
    schedule = getattr(args, "agendamento", None)
    if schedule and (sub := services.team.substitution(space_id, schedule)):
        raise InvalidInputError(
            f"Este agendamento foi assumido por {sub['nome']} (computador {sub['maquina']}) e não roda mais aqui. "
            f"Exclua-o em Arquivo › Agendamentos."
        )
    workflow, reason = services.team.official(space_id, workflow_id)
    if workflow is None:
        raise InvalidInputError(reason or "A versão oficial não está disponível.")
    services.trust.space_flow(workflow, None, space=space_id)  # a assinatura do Publicador é a conferência
    return workflow


def run(args: argparse.Namespace) -> int:
    started = datetime.now()
    name = args.fluxo
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        services = _services()
        space = SPACE_TARGET.match(args.fluxo)
        if space:  # fluxo do espaço da equipe (spec 047, RF-4752): só a versão oficial, conferida agora
            workflow = _space_official(services, args, space.group(1), space.group(2))
        else:
            workflow = find_workflow(services, args.fluxo)
        name = workflow.name
        # A mesma conferência da tela (spec 028): fluxo de fora só roda depois de aberto e confirmado no programa.
        if not space and not services.trust.opened(workflow):
            print(
                f"Recusado: '{workflow.name}' veio de fora e ainda não foi conferido neste computador.\n"
                f"Abra o fluxo no {marca().nome}, confira o que ele faz na faixa do topo e escolha Confiar e executar.",
                file=sys.stderr,
            )
            _record(
                args,
                started,
                "refused",
                name,
                "O fluxo veio de fora e ainda não foi confiado neste computador.",
            )
            return REFUSED
        print(f"{marca().nome} {__version__} · {workflow.name} ({len(workflow.nodes)} caixas)")
        runner = runner_for(services, space.group(1) if space else None)  # definições da equipe (spec 048)
        report = runner.run(workflow, args.ate, unattended=True)
    except ProdataError as exc:
        print(f"Erro: {exc.message}", file=sys.stderr)
        _record(args, started, "refused", name, exc.message)
        return REFUSED
    except (OSError, ValueError, KeyError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        _record(args, started, "refused", name, str(exc))
        return REFUSED
    failed = _print_report(workflow, report, args.silencioso)
    saved = _save_report(services.settings.storage_dir / "logs" / "execucoes", workflow, report)
    if args.relatorio:
        target = Path(args.relatorio).resolve()
        if target.suffix.lower() != ".json" or not target.parent.is_dir():
            print(
                f"Relatório não gravado: {target} precisa ser um .json numa pasta existente.", file=sys.stderr
            )
        else:
            target.write_text(report.model_dump_json(indent=1), encoding="utf-8")
    seconds = f"{report.total_elapsed_ms / 1000:.1f}".replace(".", ",")
    print(f"{'FALHOU' if failed else 'Concluído'} em {seconds} s · {failed} erro(s) · relatório: {saved}")
    first_error = next((r.error for r in report.node_results.values() if r.status == "error" and r.error), "")
    _record(args, started, "failed" if failed else "ok", name, first_error or "", report)
    return FAILED if failed else OK


def list_workflows(_args: argparse.Namespace) -> int:
    services = _services()
    for summary in services.workflows.list():
        print(f"{summary.id}\t{summary.name}\t{summary.node_count} caixas")
    return OK


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="prodata",
        description=f"{marca().nome}: sem comando, abre o servidor web. 'run' executa um fluxo e sai.",
    )
    root.add_argument("--version", action="version", version=f"{marca().nome} {__version__}")
    commands = root.add_subparsers(dest="command")
    run_cmd = commands.add_parser("run", help="Executa um fluxo e sai (para o Agendador do Windows).")
    run_cmd.add_argument("fluxo", help=f"Arquivo {SUFFIX}, ou ID ou nome de um fluxo da biblioteca.")
    run_cmd.add_argument("--ate", metavar="CAIXA", help="Executa só até esta caixa (ID).")
    run_cmd.add_argument(
        "--relatorio", metavar="ARQUIVO.json", help="Grava o relatório também neste arquivo."
    )
    run_cmd.add_argument("--silencioso", action="store_true", help="Mostra só os erros e o resumo.")
    run_cmd.add_argument(
        "--agendamento",
        metavar="ID",
        help="Execução agendada: grava o resultado no histórico dos agendamentos.",
    )
    run_cmd.set_defaults(handler=run)
    list_cmd = commands.add_parser("list", help="Lista os fluxos da biblioteca.")
    list_cmd.set_defaults(handler=list_workflows)
    commands.add_parser("serve", help="Abre o servidor web (o mesmo que não passar comando).")
    return root


def main(argv: list[str] | None = None) -> int | None:
    """Devolve o código de saída, ou None quando o pedido é abrir o servidor."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")  # acentos no console do Windows
    args = parser().parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        return None
    code: int = handler(args)
    return code


def cli_only() -> None:
    """Ponto de entrada do ``prodata-cli.exe``: nunca abre servidor."""
    code = main(sys.argv[1:] or ["--help"])
    sys.exit(OK if code is None else code)


if __name__ == "__main__":
    cli_only()
