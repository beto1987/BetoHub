"""Controlador do Refino: dados da UEX, estimativas, pedidos e aviso de pronto."""

from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from beto_hub.core.plugin_base import HubContext

from .logica.estimativas import (
    Auditoria, Estimador, Item, Metodo, mapa_metodos, minerios_de_uex, precos_refinados,
    refinarias_de_uex,
)
from .logica.pedidos import RETIRADO, Pedido, RepositorioPedidos

INTERVALO_VERIFICACAO_MS = 15_000


def _tocar_aviso() -> None:
    """Som de aviso do Windows (ou o bipe padrão em outros sistemas)."""
    if sys.platform == "win32":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return
        except Exception:
            pass
    QApplication.beep()


class ControladorRefino(QObject):
    dadosProntos = Signal()
    pedidosAlterados = Signal()
    status = Signal(str, str)  # (texto, papel)

    def __init__(self, ctx: HubContext):
        super().__init__()
        self.ctx = ctx
        self.log = ctx.log
        self.repo = RepositorioPedidos(ctx.banco)
        self.estimador: Estimador | None = None
        self.minerios: dict[str, str] = {}     # chave -> nome
        self.refinarias: dict = {}
        self.ultimo_status = ("Carregando dados de refino da UEX…", "ajuda")
        self._carregando = False

        self._timer = QTimer(self, interval=INTERVALO_VERIFICACAO_MS)
        self._timer.timeout.connect(self.verificar_prontos)
        self._timer.start()
        # Primeira verificação logo após abrir: avisa o que ficou pronto com o Hub fechado
        QTimer.singleShot(4000, lambda: self.verificar_prontos(ao_abrir=True))
        self.carregar_dados()

    # ================================================================ dados da UEX
    def carregar_dados(self, forcar: bool = False) -> None:
        uex = self.ctx.servico("uex")
        if uex is None or self._carregando:
            return
        self._carregando = True
        self._emitir_status("Carregando dados de refino da UEX…", "ajuda")
        self.ctx.workers.executar(self._baixar, uex, forcar, ao_concluir=self._ao_baixar, ao_falhar=self._ao_falhar)

    @staticmethod
    def _baixar(uex, forcar: bool) -> dict[str, Any]:
        """Roda numa thread de trabalho."""
        return {
            "metodos": uex.recurso("refineries_methods", forcar=forcar).dados or [],
            "auditorias": uex.recurso("refineries_audits", forcar=forcar).dados or [],
            "bonus": uex.recurso("refineries_yields", forcar=forcar).dados or [],
            "precos": uex.precos_todos().dados or [],
        }

    def _ao_baixar(self, d: dict[str, Any]) -> None:
        self._carregando = False
        try:
            self._processar(d)
        except Exception as erro:  # dados num formato inesperado: avisa em vez de ficar "Carregando…"
            self.log.exception("Erro ao processar os dados de refino da UEX")
            self._ao_falhar(erro)

    def _processar(self, d: dict[str, Any]) -> None:
        metodos = sorted((Metodo.de_uex(m) for m in d["metodos"] if m.get("id")), key=lambda m: m.nome)
        ids_metodo = mapa_metodos(metodos)
        auditorias = [a for a in (Auditoria.de_uex(x, ids_metodo) for x in d["auditorias"]) if a]
        self.refinarias = refinarias_de_uex(d["bonus"])
        self.minerios = minerios_de_uex(d["bonus"]) or minerios_de_uex(
            {"commodity_name": a.get("commodity_name")} for a in d["auditorias"])
        self.estimador = Estimador(metodos, auditorias, self.refinarias, precos_refinados(d["precos"]))
        unidade = "cSCU" if self.estimador.fator == 1 else "SCU"
        self.log.info("Refino: %d métodos, %d auditorias (em %s), %d refinarias, %d minérios",
                      len(metodos), len(auditorias), unidade, len(self.refinarias), len(self.minerios))
        self._emitir_status(f"{len(metodos)} métodos · {len(self.refinarias)} refinarias · "
                            f"{len(auditorias)} relatos de refino da comunidade", "ok")
        self.dadosProntos.emit()

    def _ao_falhar(self, erro: Exception) -> None:
        self._carregando = False
        self._emitir_status(f"Dados de refino indisponíveis: {erro}", "erro")

    def _emitir_status(self, texto: str, papel: str) -> None:
        self.ultimo_status = (texto, papel)
        self.status.emit(texto, papel)

    def estimar(self, id_terminal: int, itens: list[Item]):
        return self.estimador.estimar(id_terminal, itens) if self.estimador else []

    # ================================================================ pedidos
    def pedidos(self, incluir_retirados: bool = False) -> list[Pedido]:
        return self.repo.listar(incluir_retirados)

    def criar_pedido(self, p: Pedido) -> None:
        self.repo.salvar(p)
        self.log.info("Pedido de refino #%s: %s em %s (%s, %.0f min)", p.id, p.descricao_itens, p.refinaria,
                      p.metodo, p.minutos)
        self.pedidosAlterados.emit()
        self.verificar_prontos()  # caso o pedido já tenha sido criado "atrasado"

    def excluir(self, p: Pedido) -> None:
        self.repo.excluir(p.id)
        self.pedidosAlterados.emit()

    def retirar(self, p: Pedido) -> None:
        """Marca como retirado e abre o Log do Capitão pré-preenchido."""
        self.repo.definir_status(p.id, RETIRADO)
        refinado = p.refinado_scu or 0.0
        preco = (p.valor_estimado / refinado) if (p.valor_estimado and refinado) else 0.0
        self.ctx.eventos.publicar("log_capitao.registrar_refino", {
            "mercadoria": ", ".join(i.get("nome", "?") for i in p.itens),
            "origem": p.refinaria,
            "scu": round(refinado, 2),
            "preco_venda": round(preco, 2),
            "custo_extra": p.custo,
            "notas": f"Método: {p.metodo}",
        })
        self.pedidosAlterados.emit()

    def verificar_prontos(self, ao_abrir: bool = False) -> None:
        try:
            prontos = self.repo.marcar_prontos()
        except Exception:
            self.log.exception("Erro ao verificar pedidos de refino")
            return
        if not prontos:
            return
        for p in prontos:
            nomes = ", ".join(i.get("nome", "?") for i in p.itens) or "pedido"
            quando = " (ficou pronto enquanto o Hub estava fechado)" if ao_abrir else ""
            self.ctx.notificar("Refino pronto", f"{nomes} em {p.refinaria}{quando}")
        _tocar_aviso()
        self.pedidosAlterados.emit()

    def parar(self) -> None:
        self._timer.stop()
