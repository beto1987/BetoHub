"""Aba Frota: hangar do jogador com ficha técnica, nave ativa e comparador."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from beto_hub.ui.theme import repolir

from ..logica.comparacao import numero
from ..logica.hangar import NaveHangar
from .comparador import MAX_NAVES, Comparador
from .comum import COR_ACENTO
from .dialogo_nave import DialogoNave
from .ficha import FichaWidget

if TYPE_CHECKING:
    from ..controlador import ControladorFrota

COLUNAS = ["", "Nave", "Apelido", "Função", "Carga", "DPS", "Escudo", "Origem"]
ESTRELA = "★"


class AbaFrota(QWidget):
    def __init__(self, c: "ControladorFrota", parent=None):
        super().__init__(parent)
        self.c = c
        self._naves: list[NaveHangar] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        topo = QHBoxLayout()
        self.rotulo_status = QLabel()
        self.rotulo_status.setWordWrap(True)
        topo.addWidget(self.rotulo_status, 1)
        atualizar = QPushButton("Atualizar dados das naves")
        atualizar.setToolTip("Baixa de novo as estatísticas da Star Citizen Wiki (normalmente 1x por dia).")
        atualizar.clicked.connect(lambda: self.c.carregar_dados(forcar=True))
        topo.addWidget(atualizar)
        layout.addLayout(topo)

        self.abas = QTabWidget()
        self.abas.addTab(self._montar_hangar(), "HANGAR")
        self.comparador = Comparador()
        self.abas.addTab(self.comparador, "COMPARADOR")
        layout.addWidget(self.abas, 1)

        c.status.connect(self._ao_status)
        c.dadosProntos.connect(self._ao_dados)
        c.hangarAlterado.connect(self.recarregar)
        self._ao_status(*c.ultimo_status)
        self._ao_dados()

    # ================================================================ montagem
    def _montar_hangar(self) -> QWidget:
        divisor = QSplitter(Qt.Horizontal)

        esquerda = QWidget()
        v = QVBoxLayout(esquerda)
        v.setContentsMargins(0, 6, 6, 0)
        botoes = QHBoxLayout()
        self.botao_adicionar = QPushButton("+ ADICIONAR NAVE")
        self.botao_adicionar.setProperty("destaque", "true")
        self.botao_adicionar.clicked.connect(self._adicionar)
        botoes.addWidget(self.botao_adicionar)
        self.botao_ativa = QPushButton(f"{ESTRELA} Usar como nave ativa")
        self.botao_ativa.setToolTip("A nave ativa já vem selecionada no Comércio (carga) e na Mineração.")
        self.botao_ativa.clicked.connect(self._definir_ativa)
        botoes.addWidget(self.botao_ativa)
        self.botao_comparar = QPushButton("Comparar selecionadas")
        self.botao_comparar.setToolTip(f"Selecione de 2 a {MAX_NAVES} naves (Ctrl+clique) e compare lado a lado.")
        self.botao_comparar.clicked.connect(self._comparar)
        botoes.addWidget(self.botao_comparar)
        botoes.addStretch(1)
        v.addLayout(botoes)

        self.tabela = QTableWidget(0, len(COLUNAS))
        self.tabela.setHorizontalHeaderLabels(COLUNAS)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tabela.setAlternatingRowColors(True)
        cab = self.tabela.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(COLUNAS.index("Nave"), QHeaderView.Stretch)
        self.tabela.itemSelectionChanged.connect(self._ao_selecionar)
        self.tabela.itemDoubleClicked.connect(lambda *_: self._editar())
        v.addWidget(self.tabela, 1)

        self.vazio = QLabel("Seu hangar está vazio. Clique em \"+ ADICIONAR NAVE\" para cadastrar as naves que você tem.")
        self.vazio.setProperty("papel", "ajuda")
        self.vazio.setWordWrap(True)
        v.addWidget(self.vazio)

        baixo = QHBoxLayout()
        dica = QLabel(f"{ESTRELA} = nave ativa · duplo clique para editar")
        dica.setProperty("papel", "ajuda")
        baixo.addWidget(dica, 1)
        self.botao_editar = QPushButton("Editar")
        self.botao_editar.clicked.connect(self._editar)
        self.botao_remover = QPushButton("Remover")
        self.botao_remover.setProperty("perigo", "true")
        self.botao_remover.clicked.connect(self._remover)
        baixo.addWidget(self.botao_editar)
        baixo.addWidget(self.botao_remover)
        v.addLayout(baixo)

        self.ficha = FichaWidget()
        divisor.addWidget(esquerda)
        divisor.addWidget(self.ficha)
        divisor.setStretchFactor(0, 3)
        divisor.setStretchFactor(1, 2)
        return divisor

    # ================================================================ dados
    def _ao_status(self, texto: str, papel: str) -> None:
        self.rotulo_status.setText(texto)
        self.rotulo_status.setProperty("papel", papel)
        repolir(self.rotulo_status)

    def _ao_dados(self) -> None:
        self.botao_adicionar.setEnabled(bool(self.c.fichas))
        self.comparador.definir_fichas(self.c.fichas)
        self.recarregar()

    def recarregar(self, *_a) -> None:
        selecionadas = {n.id for n in self._selecionadas()}
        self._naves = self.c.hangar()
        ativa = self.c.id_ativa
        self.tabela.setRowCount(len(self._naves))
        for linha, n in enumerate(self._naves):
            f = self.c.ficha(n)
            valores = [
                ESTRELA if n.id == ativa else "", f.nome if f else n.nome, n.apelido,
                (f.funcao or f.carreira_pt) if f else "?",
                numero(f.carga_scu) if f and f.carga_scu else "—",
                numero(f.dps_total) if f and f.dps_total else "—",
                numero(f.escudo_hp) if f and f.escudo_hp else "—",
                n.origem,
            ]
            for col, texto in enumerate(valores):
                item = QTableWidgetItem(texto)
                if col == 0:
                    item.setForeground(QColor(COR_ACENTO))
                    item.setTextAlignment(Qt.AlignCenter)
                if col in (4, 5, 6):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col == 1 and f is None and self.c.fichas:
                    item.setToolTip("Nave não encontrada nos dados atuais da Star Citizen Wiki.")
                self.tabela.setItem(linha, col, item)
        self.vazio.setVisible(not self._naves)
        self.tabela.clearSelection()
        for linha, n in enumerate(self._naves):
            if n.id in selecionadas:
                self.tabela.selectRow(linha)
        if not selecionadas and self._naves:
            self.tabela.selectRow(0)
        self._ao_selecionar()

    def _selecionadas(self) -> list[NaveHangar]:
        linhas = sorted({i.row() for i in self.tabela.selectionModel().selectedRows()})
        return [self._naves[l] for l in linhas if l < len(self._naves)]

    def _ao_selecionar(self) -> None:
        sel = self._selecionadas()
        um = sel[0] if len(sel) == 1 else None
        self.botao_editar.setEnabled(um is not None)
        self.botao_remover.setEnabled(um is not None)
        self.botao_ativa.setEnabled(um is not None and um.id != self.c.id_ativa)
        self.botao_comparar.setEnabled(2 <= len(sel) <= MAX_NAVES)
        if um is not None:
            self.ficha.mostrar(self.c.ficha(um), um)
        elif not sel:
            self.ficha.mostrar(None)

    # ================================================================ ações
    def _adicionar(self) -> None:
        dlg = DialogoNave(self.c.fichas, parent=self)
        if dlg.exec() == DialogoNave.Accepted and dlg.nave:
            self.c.salvar(dlg.nave)
            self._selecionar_id(dlg.nave.id)

    def _editar(self) -> None:
        sel = self._selecionadas()
        if len(sel) != 1 or not self.c.fichas:
            return
        dlg = DialogoNave(self.c.fichas, sel[0], parent=self)
        if dlg.exec() == DialogoNave.Accepted and dlg.nave:
            self.c.salvar(dlg.nave)

    def _remover(self) -> None:
        sel = self._selecionadas()
        if len(sel) != 1:
            return
        n = sel[0]
        if QMessageBox.question(self, "Frota", f"Remover \"{n.rotulo}\" do hangar?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.c.excluir(n)

    def _definir_ativa(self) -> None:
        sel = self._selecionadas()
        if len(sel) == 1:
            self.c.definir_ativa(sel[0])

    def _comparar(self) -> None:
        uuids = [n.uuid for n in self._selecionadas()][:MAX_NAVES]
        self.comparador.comparar(uuids)
        self.abas.setCurrentWidget(self.comparador)

    def _selecionar_id(self, id_nave: int | None) -> None:
        for linha, n in enumerate(self._naves):
            if n.id == id_nave:
                self.tabela.clearSelection()
                self.tabela.selectRow(linha)
                return
