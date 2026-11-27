"""Formatação de números no padrão do idioma da interface (1.234.567,89 em português)."""

from __future__ import annotations

from beto_hub.core import i18n


def inteiro(valor: float | None) -> str:
    if valor is None:
        return "—"
    return i18n.numero(valor)


def decimal(valor: float | None, casas: int = 1) -> str:
    if valor is None:
        return "—"
    return i18n.numero(valor, casas)


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
