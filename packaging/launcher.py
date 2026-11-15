"""Ponto de entrada do executável empacotado (PyInstaller precisa de um script)."""

from prodata.desktop import main

if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()  # o leitor de PDF roda num processo filho (spec 037)
    main()
