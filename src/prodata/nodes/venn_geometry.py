"""Geometria do Venn de 2 conjuntos: círculos com área proporcional e a lente valendo a interseção."""

from __future__ import annotations

import math

__all__ = ["lens_area", "venn2_geometry"]


def lens_area(r1: float, r2: float, d: float) -> float:
    """Área da interseção de dois círculos de raios r1, r2 com centros a distância d."""
    if d >= r1 + r2:
        return 0.0
    if d <= abs(r1 - r2):
        return math.pi * min(r1, r2) ** 2
    a1 = r1**2 * math.acos((d * d + r1 * r1 - r2 * r2) / (2 * d * r1))
    a2 = r2**2 * math.acos((d * d + r2 * r2 - r1 * r1) / (2 * d * r2))
    k = 0.5 * math.sqrt((-d + r1 + r2) * (d + r1 - r2) * (d - r1 + r2) * (d + r1 + r2))
    return a1 + a2 - k


def venn2_geometry(a: float, b: float, both: float) -> dict[str, float]:
    """Raios com área proporcional a cada conjunto e distância que faz a lente valer a interseção."""
    r1, r2 = math.sqrt(a / math.pi), math.sqrt(b / math.pi)
    target = min(both, a, b)
    lo, hi = abs(r1 - r2), r1 + r2
    for _ in range(80):  # bisseção: a área da lente diminui com a distância
        mid = (lo + hi) / 2
        if lens_area(r1, r2, mid) > target:
            lo = mid
        else:
            hi = mid
    return {"r1": r1, "r2": r2, "d": (lo + hi) / 2}
