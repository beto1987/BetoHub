"""Formatação de números no padrão brasileiro (1.234.567,89)."""

from __future__ import annotations


def inteiro(valor: float | None) -> str:
    if valor is None:
        return "—"
    return f"{valor:,.0f}".replace(",", ".")


def decimal(valor: float | None, casas: int = 1) -> str:
    if valor is None:
        return "—"
    return f"{valor:,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def aUEC(valor: float | None) -> str:
    return "—" if valor is None else f"{inteiro(valor)} aUEC"


def compacto(valor: float | None) -> str:
    """245300 -> 245,3k ; 1250000 -> 1,25M"""
    if valor is None:
        return "—"
    v = abs(valor)
    sinal = "-" if valor < 0 else ""
    if v >= 1_000_000:
        return f"{sinal}{decimal(v / 1_000_000, 2)}M"
    if v >= 1_000:
        return f"{sinal}{decimal(v / 1_000, 1)}k"
    return f"{sinal}{inteiro(v)}"


CORES_RISCO = {"baixo": "#4cd98a", "médio": "#f5a623", "alto": "#ff5c5c"}
