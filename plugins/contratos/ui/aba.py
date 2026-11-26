"""Aba Contratos: contratos ativos (lidos do Game.log) e histórico com resumo."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from beto_hub.ui.theme import repolir

from ..logica.eventos import NOMES_STATUS
from ..logica.repositorio import Contrato, resumo
from .comum import CORES_STATUS, data_hora, duracao, numero
from .detalhe import DetalheContrato
from .rota import PainelRota

if TYPE_CHECKING:
    from ..controlador import ControladorContratos

COLUNAS_ATIVOS = ["Tipo", "Contrato", "Objetivos", "Aceito", "Há", "Recompensa"]
COLUNAS_HIST = ["Encerrado", "Tipo", "Contrato", "Resultado", "Duração", "Recompensa", "Log"]
PERIODOS = {"Hoje": 0, "Últimos 7 dias": 7, "Últimos 30 dias": 30, "Tudo": None}


def _inicio_periodo(dias: int | None) -> float | None:
    if dias is None:
        return None
    hoje = time.localtime()
    meia_noite = time.mktime((hoje.tm_year, hoje.tm_mon, hoje.tm_mday, 0, 0, 0, 0, 0, -1))
    return meia_noite - max(0, dias - 1) * 86400 if dias else meia_noite


def _tabela(colunas: list[str], esticar: str) -> QTableWidget:
    t = QTableWidget(0, len(colunas))
    t.setHorizontalHeaderLabels(colunas)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setAlternatingRowColors(True)
    cab = t.horizontalHeader()
    cab.setSectionResizeMode(QHeaderView.ResizeToContents)
    cab.setSectionResizeMode(colunas.index(esticar), QHeaderView.Stretch)
    return t


class _Lista(QWidget):
    """Tabela + painel de detalhes, com seleção preservada ao recarregar."""

    def __init__(self, c: "ControladorContratos", colunas: list[str], parent=None):
        super().__init__(parent)
        self.c = c
        self.contratos: list[Contrato] = []
        self.layout_principal = QVBoxLayout(self)
        self.layout_principal.setContentsMargins(0, 6, 0, 0)
        divisor = QSplitter(Qt.Horizontal)
        esquerda = QWidget()
        self.v = QVBoxLayout(esquerda)
        self.v.setContentsMargins(0, 0, 6, 0)
        self.tabela = _tabela(colunas, "Contrato")
        self.tabela.itemSelectionChanged.connect(self._ao_selecionar)
        self.v.addWidget(self.tabela, 1)
        self.vazio = QLabel()
        self.vazio.setProperty("papel", "ajuda")
        self.vazio.setWordWrap(True)
        self.v.addWidget(self.vazio)
        self.detalhe = DetalheContrato(c)
        divisor.addWidget(esquerda)
        divisor.addWidget(self.detalhe)
        divisor.setStretchFactor(0, 3)
        divisor.setStretchFactor(1, 2)
        self.layout_principal.addWidget(divisor, 1)

    def _selecionado(self) -> Contrato | None:
        linhas = self.tabela.selectionModel().selectedRows()
        return self.contratos[linhas[0].row()] if linhas and linhas[0].row() < len(self.contratos) else None

    def _ao_selecionar(self) -> None:
        self.detalhe.mostrar(self._selecionado())

    def preencher(self, contratos: list[Contrato], linhas: list[list[tuple[str, str | None]]]) -> None:
        anterior = self._selecionado()
        self.contratos = contratos
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(linhas))
        for i, valores in enumerate(linhas):
            for j, (texto, cor) in enumerate(valores):
                item = QTableWidgetItem(texto)
                if cor:
                    item.setForeground(QColor(cor))
                if self.tabela.horizontalHeaderItem(j).text() in ("Recompensa", "Objetivos"):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabela.setItem(i, j, item)
        self.tabela.clearSelection()
        missoes = [c.missao for c in contratos]
        if anterior and anterior.missao in missoes:
            self.tabela.selectRow(missoes.index(anterior.missao))
        elif contratos:
            self.tabela.selectRow(0)
        self.tabela.blockSignals(False)
        self._ao_selecionar()
        self.vazio.setVisible(not contratos)


class AbaContratos(QWidget):
    def __init__(self, c: "ControladorContratos", parent=None):
        super().__init__(parent)
        self.c = c
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        topo = QHBoxLayout()
        self.rotulo_status = QLabel()
        self.rotulo_status.setWordWrap(True)
        topo.addWidget(self.rotulo_status, 1)
        importar = QPushButton("Importar histórico")
        importar.setToolTip("Lê os logs das suas sessões anteriores (pasta logbackups do jogo).")
        importar.clicked.connect(self._importar)
        topo.addWidget(importar)
        layout.addLayout(topo)

        self.abas = QTabWidget()
        self.ativos = _Lista(c, COLUNAS_ATIVOS)
        self.ativos.vazio.setText(
            "Nenhum contrato ativo. Aceite um contrato no jogo: ele aparece aqui sozinho em poucos segundos "
            "(o Hub lê o Game.log do Star Citizen, sem tocar no jogo).")
        self.abas.addTab(self.ativos, "ATIVOS")
        self.historico = _Lista(c, COLUNAS_HIST)
        self._montar_filtros_historico()
        self.abas.addTab(self.historico, "HISTÓRICO")
        self.rota = PainelRota(c)
        self.abas.addTab(self.rota, "ROTA DE ENTREGAS")
        layout.addWidget(self.abas, 1)

        c.status.connect(self._ao_status)
        c.contratosAlterados.connect(self.recarregar)
        self._ao_status(*c.ultimo_status)
        self.recarregar()

    def _montar_filtros_historico(self) -> None:
        h = self.historico
        barra = QHBoxLayout()
        barra.addWidget(QLabel("Período:"))
        self.periodo = QComboBox()
        self.periodo.addItems(list(PERIODOS))
        self.periodo.setCurrentText("Últimos 30 dias")
        self.periodo.currentIndexChanged.connect(self.recarregar)
        barra.addWidget(self.periodo)
        barra.addWidget(QLabel("Resultado:"))
        self.filtro_status = QComboBox()
        self.filtro_status.addItem("Todos", "")
        for chave, nome in NOMES_STATUS.items():
            if chave != "ativo":
                self.filtro_status.addItem(nome, chave)
        self.filtro_status.currentIndexChanged.connect(self.recarregar)
        barra.addWidget(self.filtro_status)
        self.filtro_tipo = QComboBox()
        self.filtro_tipo.addItem("Todos os tipos", "")
        self.filtro_tipo.currentIndexChanged.connect(self.recarregar)
        barra.addWidget(self.filtro_tipo)
        barra.addStretch(1)
        h.layout_principal.insertLayout(0, barra)
        self.resumo = QLabel()
        self.resumo.setTextFormat(Qt.RichText)
        h.layout_principal.insertWidget(1, self.resumo)
        h.vazio.setText("Nenhum contrato encerrado neste período. Use \"Importar histórico\" para trazer "
                        "os contratos das suas sessões anteriores.")

    # ================================================================ dados
    def _ao_status(self, texto: str, papel: str) -> None:
        self.rotulo_status.setText(texto)
        self.rotulo_status.setProperty("papel", papel)
        repolir(self.rotulo_status)

    def _importar(self) -> None:
        if not self.c.importar_historico():
            self._ao_status("Aguarde a leitura atual terminar e tente de novo.", "alerta")

    def recarregar(self, *_a) -> None:
        ativos = self.c.ativos()
        linhas = []
        for c in ativos:
            feitos, total = c.progresso
            linhas.append([(c.tipo, None), (c.rotulo, None), (f"{feitos}/{total}" if total else "—", None),
                           (data_hora(c.aceito_em), None), (duracao(c.duracao_s), None),
                           (numero(c.recompensa) if c.recompensa else "—", None)])
        self.ativos.preencher(ativos, linhas)
        self.abas.setTabText(0, f"ATIVOS ({len(ativos)})")

        todos = self.c.historico(_inicio_periodo(PERIODOS[self.periodo.currentText()]))
        tipos = sorted({c.tipo for c in todos if c.tipo})
        tipo_atual = self.filtro_tipo.currentData()
        self.filtro_tipo.blockSignals(True)
        self.filtro_tipo.clear()
        self.filtro_tipo.addItem("Todos os tipos", "")
        for t in tipos:
            self.filtro_tipo.addItem(t, t)
        self.filtro_tipo.setCurrentIndex(max(0, self.filtro_tipo.findData(tipo_atual)))
        self.filtro_tipo.blockSignals(False)

        status, tipo = self.filtro_status.currentData(), self.filtro_tipo.currentData()
        hist = [c for c in todos if (not status or c.status == status) and (not tipo or c.tipo == tipo)]
        linhas = []
        for c in hist:
            cor = CORES_STATUS.get(c.status)
            linhas.append([(data_hora(c.encerrado_em), None), (c.tipo, None), (c.rotulo, None),
                           (NOMES_STATUS.get(c.status, c.status), cor), (duracao(c.duracao_s), None),
                           (numero(c.recompensa) if c.recompensa else "—", None),
                           ("✔" if c.registrado_log else "", "#4cd98a")])
        self.historico.preencher(hist, linhas)

        r = resumo(hist)
        taxa = "—" if r["taxa"] is None else f"{r['taxa'] * 100:.0f}%"
        recompensas = (f"{numero(r['recompensas'])} aUEC <span style='color:#7f98ad'>"
                       f"(em {r['com_recompensa']} de {r['concluidos']} concluídos)</span>")
        self.resumo.setText(
            f"<span style='color:#7f98ad'>Contratos:</span> <b>{r['total']}</b> &nbsp;·&nbsp; "
            f"<span style='color:#7f98ad'>Concluídos:</span> <b style='color:#4cd98a'>{r['concluidos']}</b> &nbsp;·&nbsp; "
            f"<span style='color:#7f98ad'>Taxa de sucesso:</span> <b>{taxa}</b> &nbsp;·&nbsp; "
            f"<span style='color:#7f98ad'>Recompensas informadas:</span> <b>{recompensas}</b>")
