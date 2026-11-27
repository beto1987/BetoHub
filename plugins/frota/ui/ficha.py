"""Ficha técnica de uma nave: estatísticas do loadout de fábrica e armas."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from beto_hub.core.i18n import tr
from ..logica.comparacao import ATRIBUTOS, TEXTO_FICHA, numero
from ..logica.hangar import NaveHangar
from ..logica.naves import FichaNave
from .comum import COR_ACENTO, COR_SUAVE


class FichaWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.titulo = QLabel()
        self.titulo.setProperty("papel", "titulo")
        self.titulo.setWordWrap(True)
        layout.addWidget(self.titulo)
        self.subtitulo = QLabel()
        self.subtitulo.setProperty("papel", "ajuda")
        self.subtitulo.setWordWrap(True)
        layout.addWidget(self.subtitulo)

        self.tabela = QTableWidget(0, 2)
        self.tabela.horizontalHeader().setVisible(False)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabela.setShowGrid(False)
        cab = self.tabela.horizontalHeader()
        cab.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.tabela, 1)
        self.mostrar(None)

    def mostrar(self, ficha: FichaNave | None, nave: NaveHangar | None = None) -> None:
        self.tabela.setRowCount(0)
        if ficha is None:
            self.titulo.setText(tr("FICHA DA NAVE"))
            self.subtitulo.setText(
                tr("Selecione uma nave do hangar para ver as estatísticas.") if nave is None else
                tr("\"{nave}\" não foi encontrada nos dados da Star Citizen Wiki.", nave=nave.nome))
            return

        self.titulo.setText((nave.apelido.upper() + " · " if nave and nave.apelido else "") + ficha.nome.upper())
        detalhes = [ficha.nome_jogo if ficha.nome_jogo != ficha.nome else "",
                    tr("veículo terrestre") if ficha.terrestre else "",
                    tr("conceito (ainda não voa)") if ficha.status == "in-concept" else "",
                    tr("loadout de fábrica · dados do jogo {versao}", versao=ficha.versao) if ficha.versao else tr("loadout de fábrica")]
        if nave and nave.origem:
            detalhes.append(tr(nave.origem))
        self.subtitulo.setText(" · ".join(d for d in detalhes if d))

        grupo_atual = ""
        for a in ATRIBUTOS:
            if a.grupo != grupo_atual:
                grupo_atual = a.grupo
                self._linha_grupo(tr(a.grupo).upper())
            texto = TEXTO_FICHA.get(a.rotulo, a.texto)(ficha)
            self._linha(tr(a.rotulo), texto, tr(a.dica) if a.dica else "")
            if a.rotulo == "Dano dos mísseis":
                self._armas(ficha)
        if nave and nave.notas:
            self._linha_grupo(tr("NOTAS"))
            self._linha("", nave.notas)

    # ------------------------------------------------------------ linhas
    def _linha_grupo(self, texto: str) -> None:
        linha = self.tabela.rowCount()
        self.tabela.insertRow(linha)
        item = QTableWidgetItem(texto)
        fonte = QFont(item.font())
        fonte.setBold(True)
        item.setFont(fonte)
        item.setForeground(QColor(COR_ACENTO))
        self.tabela.setItem(linha, 0, item)
        self.tabela.setSpan(linha, 0, 1, 2)

    def _linha(self, rotulo: str, texto: str, dica: str = "") -> None:
        linha = self.tabela.rowCount()
        self.tabela.insertRow(linha)
        r = QTableWidgetItem(rotulo)
        r.setForeground(QColor(COR_SUAVE))
        v = QTableWidgetItem(texto)
        v.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        if dica:
            r.setToolTip(dica)
            v.setToolTip(dica)
        self.tabela.setItem(linha, 0, r)
        self.tabela.setItem(linha, 1, v)

    def _armas(self, ficha: FichaNave) -> None:
        if not ficha.armas:
            return
        texto = "\n".join(tr("{n}× {arma} — {dps} DPS cada", n=a.quantidade, arma=a.nome, dps=numero(a.dps))
                          for a in ficha.armas)
        self._linha(tr("Armas do piloto"), texto)
        self.tabela.resizeRowToContents(self.tabela.rowCount() - 1)
