"""Formatação e cores usadas pelas telas dos Contratos."""

from __future__ import annotations

import time

from ..logica.eventos import ABANDONADO, ATIVO, CONCLUIDO, DESATIVADO, FALHOU, SEM_FIM

CORES_STATUS = {ATIVO: "#35c8f5", CONCLUIDO: "#4cd98a", FALHOU: "#ff5c5c", ABANDONADO: "#f5a623",
                DESATIVADO: "#7f98ad", SEM_FIM: "#7f98ad"}
COR_SUAVE = "#7f98ad"
COR_TEXTO = "#d6e6f2"


def numero(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}".replace(",", ".")


def duracao(segundos: float | None) -> str:
    if segundos is None:
        return "—"
    minutos = int(segundos // 60)
    if minutos < 60:
        return f"{minutos} min"
    horas, minutos = divmod(minutos, 60)
    if horas < 48:
        return f"{horas} h {minutos:02d}"
    return f"{horas // 24} dias"


def data_hora(epoch: float | None) -> str:
    return time.strftime("%d/%m %H:%M", time.localtime(epoch)) if epoch else "—"
