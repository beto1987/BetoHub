"""Barramento de eventos: o jeito dos módulos conversarem sem se importarem.

Exemplo:
    ctx.eventos.assinar("mineracao.minerio_identificado", self._ao_identificar)
    ctx.eventos.publicar("mineracao.minerio_identificado", {"minerio": "Quantanium"})

Pode publicar de qualquer thread: os callbacks sempre rodam na thread da
interface (o sinal Qt é entregue em fila), então podem mexer em widgets.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot

from .logging_setup import obter_logger

log = obter_logger("eventos")

Callback = Callable[[Any], None]


class BarramentoEventos(QObject):
    _sinal = Signal(str, object)

    def __init__(self):
        super().__init__()
        self._assinantes: dict[str, list[Callback]] = defaultdict(list)
        self._sinal.connect(self._despachar)

    def publicar(self, nome: str, dados: Any = None) -> None:
        log.debug("Evento publicado: %s", nome)
        self._sinal.emit(nome, dados)

    def assinar(self, nome: str, callback: Callback) -> None:
        """Use nome "*" para receber todos os eventos (callback recebe (nome, dados))."""
        self._assinantes[nome].append(callback)

    def cancelar(self, nome: str, callback: Callback) -> None:
        if callback in self._assinantes.get(nome, []):
            self._assinantes[nome].remove(callback)

    @Slot(str, object)
    def _despachar(self, nome: str, dados: Any) -> None:
        for callback in list(self._assinantes.get(nome, [])):
            self._chamar(callback, nome, dados)
        for callback in list(self._assinantes.get("*", [])):
            self._chamar(callback, nome, (nome, dados))

    @staticmethod
    def _chamar(callback: Callback, nome: str, dados: Any) -> None:
        try:
            callback(dados)
        except Exception:  # um assinante com erro não derruba os outros
            log.exception("Erro no assinante do evento %s", nome)
