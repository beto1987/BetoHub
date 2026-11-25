"""Execução de tarefas em segundo plano (HTTP, OCR, cálculos pesados).

Regra de ouro: nada demorado na thread da interface. Uso:

    ctx.workers.executar(
        buscar_precos, "Laranite",
        ao_concluir=self._mostrar_precos,   # roda na thread da interface
        ao_falhar=self._mostrar_erro,       # recebe a exceção
    )
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from .logging_setup import obter_logger

log = obter_logger("workers")


class _Sinais(QObject):
    concluido = Signal(object)
    falhou = Signal(object)
    terminou = Signal()


class _Tarefa(QRunnable):
    def __init__(self, funcao: Callable, args: tuple, kwargs: dict, sinais: _Sinais):
        super().__init__()
        self.funcao, self.args, self.kwargs, self.sinais = funcao, args, kwargs, sinais

    def run(self) -> None:  # roda numa thread do pool
        try:
            resultado = self.funcao(*self.args, **self.kwargs)
        except Exception as erro:
            log.exception("Tarefa em segundo plano falhou: %s", getattr(self.funcao, "__name__", self.funcao))
            self.sinais.falhou.emit(erro)
        else:
            self.sinais.concluido.emit(resultado)
        finally:
            self.sinais.terminou.emit()


class GerenciadorTarefas:
    def __init__(self, max_threads: int = 4):
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(max_threads)
        self._ativos: set[_Sinais] = set()  # segura referências até terminar

    def executar(
        self,
        funcao: Callable[..., Any],
        *args,
        ao_concluir: Callable[[Any], None] | None = None,
        ao_falhar: Callable[[Exception], None] | None = None,
        **kwargs,
    ) -> None:
        # Criado na thread da interface -> os sinais são entregues nela.
        sinais = _Sinais()
        if ao_concluir:
            sinais.concluido.connect(ao_concluir)
        if ao_falhar:
            sinais.falhou.connect(ao_falhar)
        sinais.terminou.connect(lambda s=sinais: self._ativos.discard(s))
        self._ativos.add(sinais)
        self._pool.start(_Tarefa(funcao, args, kwargs, sinais))

    def aguardar(self, ms: int = 3000) -> bool:
        """Espera as tarefas terminarem (usado ao fechar o app)."""
        return self._pool.waitForDone(ms)
