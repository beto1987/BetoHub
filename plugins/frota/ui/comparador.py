"""Comparador: até 4 naves lado a lado, com o melhor valor de cada linha destacado."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..logica.comparacao import ATRIBUTOS, melhores
from ..logica.naves import FichaNave
from .comum import COR_ACENTO, COR_OK, COR_SUAVE, combo_pesquisavel, preencher_naves

MAX_NAVES = 4
NENHUMA = "— nenhuma —"


class Comparador(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fichas: list[FichaNave] = []
        self._por_uuid: dict[str, FichaNave] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        topo = QHBoxLayout()
        self.combos: list[QComboBox] = []
        for i in range(MAX_NAVES):
            c = QComboBox()
            combo_pesquisavel(c)
            c.setMinimumWidth(180)
            c.currentIndexChanged.connect(self._atualizar)
            topo.addWidget(c, 1)
            self.combos.append(c)
        limpar = QPushButton("Limpar")
        limpar.clicked.connect(self.limpar)
        topo.addWidget(limpar)
        layout.addLayout(topo)

        dica = QLabel("Escolha de 2 a 4 naves (qualquer nave, não só as do hangar). "
                      "O melhor valor de cada linha fica em verde. Estatísticas do loadout de fábrica.")
        dica.setProperty("papel", "ajuda")
        dica.setWordWrap(True)
        layout.addWidget(dica)

        self.tabela = QTableWidget(0, 1)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabela.setAlternatingRowColors(True)
        layout.addWidget(self.tabela, 1)

    # ------------------------------------------------------------ dados
    def definir_fichas(self, fichas: list[FichaNave]) -> None:
        self.fichas = fichas
        self._por_uuid = {f.uuid: f for f in fichas}
        for c in self.combos:
            preencher_naves(c, fichas, vazio=NENHUMA, manter_uuid=c.currentData() or "")
        self._atualizar()

    def comparar(self, uuids: list[str]) -> None:
        """Pré-seleciona as naves (usado pelo botão "Comparar" do hangar)."""
        for i, c in enumerate(self.combos):
            uuid = uuids[i] if i < len(uuids) else ""
            c.blockSignals(True)
            c.setCurrentIndex(max(0, c.findData(uuid)))
            c.blockSignals(False)
        self._atualizar()

    def limpar(self) -> None:
        self.comparar([])

    # ------------------------------------------------------------ tabela
    def _atualizar(self, *_a) -> None:
        escolhidas = [self._por_uuid[c.currentData()] for c in self.combos if c.currentData() in self._por_uuid]
        self.tabela.clear()
        self.tabela.setColumnCount(1 + len(escolhidas))
        self.tabela.setHorizontalHeaderLabels([""] + [f.nome for f in escolhidas])
        self.tabela.setRowCount(0)
        if not escolhidas:
            return

        grupo_atual = ""
        for a in ATRIBUTOS:
            if a.grupo != grupo_atual:
                grupo_atual = a.grupo
                self._linha_grupo(a.grupo.upper(), len(escolhidas))
            linha = self.tabela.rowCount()
            self.tabela.insertRow(linha)
            rotulo = QTableWidgetItem(a.rotulo)
            rotulo.setForeground(QColor(COR_SUAVE))
            if a.dica:
                rotulo.setToolTip(a.dica)
            self.tabela.setItem(linha, 0, rotulo)
            destaque = melhores(escolhidas, a)
            for i, f in enumerate(escolhidas):
                item = QTableWidgetItem(a.texto(f))
                item.setTextAlignment(Qt.AlignCenter)
                if i in destaque:
                    item.setForeground(QColor(COR_OK))
                    fonte = QFont(item.font())
                    fonte.setBold(True)
                    item.setFont(fonte)
                self.tabela.setItem(linha, i + 1, item)

        cab = self.tabela.horizontalHeader()
        cab.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for i in range(len(escolhidas)):
            cab.setSectionResizeMode(i + 1, QHeaderView.Stretch)

    def _linha_grupo(self, texto: str, colunas: int) -> None:
        linha = self.tabela.rowCount()
        self.tabela.insertRow(linha)
        item = QTableWidgetItem(texto)
        fonte = QFont(item.font())
        fonte.setBold(True)
        item.setFont(fonte)
        item.setForeground(QColor(COR_ACENTO))
        self.tabela.setItem(linha, 0, item)
        self.tabela.setSpan(linha, 0, 1, colunas + 1)
