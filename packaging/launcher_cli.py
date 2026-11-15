"""Ponto de entrada do ``prodata-cli.exe`` (spec 033): linha de comando, com console, sem abrir janela."""

from prodata.cli import cli_only

if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()  # o leitor de PDF roda num processo filho (spec 037)
    cli_only()
