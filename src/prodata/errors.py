"""Erros de domínio. A API traduz ``code`` em status HTTP; o motor não conhece HTTP."""

from __future__ import annotations


class ProdataError(Exception):
    code = "invalid"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ProdataError):
    code = "not_found"


class ConflictError(ProdataError):
    code = "conflict"


class InvalidInputError(ProdataError):
    code = "invalid"


class TooLargeError(ProdataError):
    code = "too_large"


class MemoryAskError(ProdataError):
    """A leitura vai passar de 1/4 da memória do computador: a tela pergunta Parar ou Continuar assim mesmo
    (spec 049, RF-4957). A resposta vale só para aquela execução."""

    code = "memory"

    def __init__(self, message: str, estimate: int, memory: int) -> None:
        super().__init__(message)
        self.estimate = estimate
        self.memory = memory
