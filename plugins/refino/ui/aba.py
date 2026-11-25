"""Aba Refino: pedidos com contagem regressiva, retirada (-> Log) e novo pedido."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from beto_hub.ui.theme import repolir

from ..logica.estimativas import formatar_minutos
from ..logica.pedidos import ANDAMENTO, NOMES_STATUS, PRONTO, RETIRADO, Pedido
from .dialogo_pedido import DialogoPedido, _n

if TYPE_CHECKING:
    from ..controlador import ControladorRefino

COLUNAS = ["Status", "Refinaria", "Minérios", "Método", "Pronto às", "Falta", "Custo", "Lucro estimado", "Notas"]
CORES = {ANDAMENTO: "#35c8f5", PRONTO: "#4cd98a", RETIRADO: "#7f98ad"}


def abrir_novo_pedido(c: "ControladorRefino", parent=None) -> None:
    """Usado pela aba e pelo overlay."""
    dlg = DialogoPedido(c, parent)
    dlg.raise_()
    dlg.activateWindow()
    if dlg.exec() == DialogoPedido.Accepted and dlg.pedido:
        c.criar_pedido(dlg.pedido)


class AbaRefino(QWidget):
    def __init__(self, c: "ControladorRefino", parent=None):
        super().__init__(parent)
        self.c = c
        self._pedidos: list[Pedido] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        topo = QHBoxLayout()
        novo = QPushButton("+ NOVO PEDIDO DE REFINO")
        novo.setProperty("destaque", "true")
        novo.clicked.connect(lambda: abrir_novo_pedido(self.c, self))
        topo.addWidget(novo)
        atualizar = QPushButton("Atualizar dados da UEX")
        atualizar.clicked.connect(lambda: self.c.carregar_dados(forcar=True))
        topo.addWidget(atualizar)
        self.rotulo_status = QLabel()
        self.rotulo_status.setWordWrap(True)
        topo.addWidget(self.rotulo_status, 1)
        layout.addLayout(topo)

        self.tabela = QTableWidget(0, len(COLUNAS))
        self.tabela.setHorizontalHeaderLabels(COLUNAS)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.setAlternatingRowColors(True)
        cab = self.tabela.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(COLUNAS.index("Minérios"), QHeaderView.Stretch)
        self.tabela.itemSelectionChanged.connect(self._ao_selecionar)
        layout.addWidget(self.tabela, 1)

        baixo = QHBoxLayout()
        self.mostrar_retirados = QCheckBox("Mostrar retirados")
        self.mostrar_retirados.toggled.connect(self.recarregar)
        baixo.addWidget(self.mostrar_retirados)
        dica = QLabel("Quando o refino ficar pronto, o Windows avisa com som e balão — mesmo com o jogo em tela.")
        dica.setProperty("papel", "ajuda")
        baixo.addWidget(dica, 1)
        self.botao_retirar = QPushButton("Retirado / vendido → Log do Capitão")
        self.botao_retirar.clicked.connect(self._retirar)
        self.botao_excluir = QPushButton("Excluir")
        self.botao_excluir.setProperty("perigo", "true")
        self.botao_excluir.clicked.connect(self._excluir)
        baixo.addWidget(self.botao_retirar)
        baixo.addWidget(self.botao_excluir)
        layout.addLayout(baixo)

        c.pedidosAlterados.connect(self.recarregar)
        c.status.connect(self._ao_status)
        self._ao_status(*c.ultimo_status)

        # Contagem regressiva: atualiza a coluna "Falta" a cada segundo
        self._relogio = QTimer(self, interval=1000)
        self._relogio.timeout.connect(self._atualizar_contagem)
        self._relogio.start()
        self.recarregar()

    # ------------------------------------------------------------ dados
    def recarregar(self, *_a) -> None:
        selecionado = self._selecionado()
        self._pedidos = self.c.pedidos(self.mostrar_retirados.isChecked())
        self.tabela.setRowCount(len(self._pedidos))
        for linha, p in enumerate(self._pedidos):
            fim = time.strftime("%d/%m %H:%M", time.localtime(p.fim))
            lucro = p.lucro_estimado
            valores = [NOMES_STATUS.get(p.status, p.status), p.refinaria, p.descricao_itens, p.metodo or "—",
                       fim, "", _n(p.custo), _n(lucro), p.notas]
            for col, texto in enumerate(valores):
                item = QTableWidgetItem(texto)
                if col == 0:
                    item.setForeground(QColor(CORES.get(p.status, "#d6e6f2")))
                if col in (6, 7):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col == 7 and lucro is not None:
                    item.setForeground(QColor("#4cd98a" if lucro >= 0 else "#ff5c5c"))
                    item.setToolTip("Valor estimado do refinado menos o custo do refino.")
                self.tabela.setItem(linha, col, item)
        self._atualizar_contagem()
        if selecionado:
            ids = [p.id for p in self._pedidos]
            if selecionado.id in ids:
                self.tabela.selectRow(ids.index(selecionado.id))
        self._ao_selecionar()

    def _atualizar_contagem(self) -> None:
        agora = time.time()
        col = COLUNAS.index("Falta")
        for linha, p in enumerate(self._pedidos):
            if p.status == ANDAMENTO:
                restante = p.restante_s(agora)
                texto = formatar_minutos(restante / 60) if restante >= 60 else f"{int(restante)} s"
            else:
                texto = "—" if p.status == RETIRADO else "pronto!"
            item = self.tabela.item(linha, col)
            if item:
                item.setText(texto)

    def _selecionado(self) -> Pedido | None:
        linhas = self.tabela.selectionModel().selectedRows()
        return self._pedidos[linhas[0].row()] if linhas and linhas[0].row() < len(self._pedidos) else None

    def _ao_selecionar(self) -> None:
        p = self._selecionado()
        self.botao_retirar.setEnabled(p is not None and p.status != RETIRADO)
        self.botao_excluir.setEnabled(p is not None)

    def _ao_status(self, texto: str, papel: str) -> None:
        self.rotulo_status.setText(texto)
        self.rotulo_status.setProperty("papel", papel)
        repolir(self.rotulo_status)

    # ------------------------------------------------------------ ações
    def _retirar(self) -> None:
        p = self._selecionado()
        if not p:
            return
        aviso = "" if p.status == PRONTO else "\n\nAtenção: pelo relógio do Hub este pedido ainda não ficou pronto."
        if QMessageBox.question(self, "Refino", f"Marcar \"{p.descricao_itens}\" em {p.refinaria} como retirado "
                                f"e registrar no Log do Capitão?{aviso}") == QMessageBox.Yes:
            self.c.retirar(p)

    def _excluir(self) -> None:
        p = self._selecionado()
        if p and QMessageBox.question(self, "Refino", f"Excluir o pedido \"{p.descricao_itens}\" em {p.refinaria}?\n"
                                      "Essa ação não pode ser desfeita.",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.c.excluir(p)
