"""Planejador de rota: paradas das entregas (lidas dos objetivos) e a melhor ordem para visitá-las."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QCompleter, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from beto_hub.core.i18n import N_, tr
from ..logica.rota import COLETA, Local, Parada, Rota
from .comum import COR_SUAVE

if TYPE_CHECKING:
    from ..controlador import ControladorContratos

COLUNAS = ["", N_("Tipo"), N_("Carga"), N_("Local"), N_("Contrato")]
ESCOLHA = N_("— escolha o local —")
COR_ALERTA = "#f5a623"


def _combo_locais(locais: list[Local], vazio: str) -> QComboBox:
    combo = QComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    completer = combo.completer()
    completer.setFilterMode(Qt.MatchContains)
    completer.setCompletionMode(QCompleter.PopupCompletion)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    combo.addItem(vazio, None)
    for l in locais:
        combo.addItem(l.rotulo, l)
    return combo


def _selecionar(combo: QComboBox, local: Local | None) -> None:
    alvo = local.id_terminal if local else None
    for i in range(combo.count()):
        dado = combo.itemData(i)
        if (dado.id_terminal if dado else None) == alvo:
            combo.setCurrentIndex(i)
            return
    combo.setCurrentIndex(0)


def html_rota(rota: Rota, compacto: bool = False) -> str:
    if not rota.trechos:
        return f"<span style='color:{COR_SUAVE}'>{tr('Nenhuma parada com local definido.')}</span>"
    partes = []
    for n, t in enumerate(rota.trechos, 1):
        dist = "" if t.distancia is None else f" <span style='color:{COR_SUAVE}'>· {t.distancia:g} Gm</span>"
        partes.append(f"<div style='margin-top:4px;'><b style='color:#35c8f5'>{n}. {html.escape(t.local.rotulo)}</b>{dist}</div>")
        for p in t.paradas:
            cor = COR_ALERTA if p.tipo == COLETA else "#d6e6f2"
            contrato = "" if compacto else f" <span style='color:{COR_SUAVE}'>· {html.escape(p.contrato)}</span>"
            partes.append(f"<div style='color:{cor}; margin-left:14px;'>▸ {html.escape(p.descricao)}{contrato}</div>")
    total = ""
    if rota.total_valido:
        total = f"<div style='margin-top:8px;'><b>{tr('Total: {gm} Gm', gm=f'{rota.total_gm:g}')}</b>"
        if not rota.exata:
            total += f" <span style='color:{COR_SUAVE}'>{tr('(aproximado)')}</span>"
        total += "</div>"
    avisos = "".join(f"<div style='color:{COR_ALERTA}'>⚠ {html.escape(a)}</div>" for a in rota.avisos)
    return "".join(partes) + total + avisos


class PainelRota(QWidget):
    def __init__(self, c: "ControladorContratos", parent=None):
        super().__init__(parent)
        self.c = c
        self.paradas: list[Parada] = []
        self._escolhas: dict[tuple[str, str, str], tuple[bool, Local | None]] = {}  # ajustes do jogador
        self._combos: list[QComboBox] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        topo = QHBoxLayout()
        topo.addWidget(QLabel(tr("Estou em:")))
        self.inicio = _combo_locais([], tr("— qualquer lugar (começa na 1ª parada) —"))
        self.inicio.setMinimumWidth(320)
        topo.addWidget(self.inicio, 1)
        recarregar = QPushButton(tr("Recarregar paradas"))
        recarregar.setToolTip(tr("Lê de novo as entregas pendentes dos contratos ativos."))
        recarregar.clicked.connect(self.recarregar)
        topo.addWidget(recarregar)
        self.botao_calcular = QPushButton(tr("CALCULAR MELHOR ROTA"))
        self.botao_calcular.setProperty("destaque", "true")
        self.botao_calcular.clicked.connect(self.calcular)
        topo.addWidget(self.botao_calcular)
        layout.addLayout(topo)

        dica = QLabel(tr("As paradas vêm dos objetivos dos contratos de transporte ativos (\"Deliver … to …\"). "
                         "Quando o jogo só diz o sistema (ex.: \"Pyro System\") ou o local não está na UEX, escolha o "
                         "local na lista — ele aparece no seu mobiGlas. Distâncias da UEX."))
        dica.setWordWrap(True)
        dica.setProperty("papel", "ajuda")
        layout.addWidget(dica)

        divisor = QSplitter(Qt.Horizontal)
        self.tabela = QTableWidget(0, len(COLUNAS))
        self.tabela.setHorizontalHeaderLabels([tr(c) if c else c for c in COLUNAS])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setSelectionMode(QAbstractItemView.NoSelection)
        cab = self.tabela.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(COLUNAS.index("Local"), QHeaderView.Stretch)
        self.tabela.itemChanged.connect(self._ao_marcar)
        divisor.addWidget(self.tabela)

        direita = QWidget()
        v = QVBoxLayout(direita)
        v.setContentsMargins(6, 0, 0, 0)
        titulo = QLabel(tr("MELHOR ROTA"))
        titulo.setProperty("papel", "titulo")
        v.addWidget(titulo)
        self.resultado = QLabel()
        self.resultado.setTextFormat(Qt.RichText)
        self.resultado.setWordWrap(True)
        self.resultado.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        v.addWidget(self.resultado, 1)
        divisor.addWidget(direita)
        divisor.setStretchFactor(0, 3)
        divisor.setStretchFactor(1, 2)
        layout.addWidget(divisor, 1)

        c.locaisProntos.connect(self._ao_locais)
        c.contratosAlterados.connect(self.recarregar)
        c.rotaCalculada.connect(self._ao_rota)
        self._ao_locais()

    # ------------------------------------------------------------ dados
    def _locais(self) -> list[Local]:
        return self.c.indice.todos() if self.c.indice else []

    def _ao_locais(self) -> None:
        locais = self._locais()
        atual = self.inicio.currentData()
        self.inicio.clear()
        self.inicio.addItem(tr("— qualquer lugar (começa na 1ª parada) —"), None)
        for l in locais:
            self.inicio.addItem(l.rotulo, l)
        salvo = atual or next((l for l in locais if l.id_terminal == int(self.c.opcao("local_atual") or 0)), None)
        _selecionar(self.inicio, salvo)
        self.recarregar()
        if not self.c.indice:
            self.resultado.setText(f"<span style='color:{COR_SUAVE}'>{tr('Carregando os locais da UEX…')}</span>")
        elif not self.c.ultima_rota:
            self.resultado.setText(f"<span style='color:{COR_SUAVE}'>{tr('Clique em "Calcular melhor rota".')}</span>")

    @staticmethod
    def _chave(p: Parada) -> tuple[str, str, str]:
        return (p.missao, p.tipo, p.objetivo or p.texto_local)

    def recarregar(self, *_a) -> None:
        self._guardar_escolhas()
        self.paradas = self.c.paradas()
        for p in self.paradas:
            if self._chave(p) in self._escolhas:
                p.incluir, local = self._escolhas[self._chave(p)]
                p.local = local or p.local
        locais = self._locais()
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(self.paradas))
        self._combos = []
        for i, p in enumerate(self.paradas):
            marca = QTableWidgetItem()
            marca.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            marca.setCheckState(Qt.Checked if p.incluir else Qt.Unchecked)
            self.tabela.setItem(i, 0, marca)
            tipo = QTableWidgetItem(tr("Coleta") if p.tipo == COLETA else tr("Entrega"))
            if p.tipo == COLETA:
                tipo.setForeground(QColor(COR_ALERTA))
            self.tabela.setItem(i, 1, tipo)
            self.tabela.setItem(i, 2, QTableWidgetItem(f"{p.scu:g} SCU {p.carga}" if p.scu else p.carga))
            combo = _combo_locais(locais, tr(ESCOLHA))
            _selecionar(combo, p.local)
            combo.setToolTip(tr("No jogo: {local}", local=p.texto_local))
            if p.local is None:
                combo.setStyleSheet(f"QComboBox {{ border: 1px solid {COR_ALERTA}; }}")
                combo.lineEdit().setPlaceholderText(tr("{local} — escolha o local", local=p.texto_local))
                combo.setCurrentIndex(-1)
            combo.currentIndexChanged.connect(lambda _i, linha=i: self._ao_escolher_local(linha))
            self.tabela.setCellWidget(i, 3, combo)
            self._combos.append(combo)
            self.tabela.setItem(i, 4, QTableWidgetItem(p.contrato))
        self.tabela.blockSignals(False)
        self.botao_calcular.setEnabled(bool(self.paradas) and self.c.indice is not None)
        if not self.paradas:
            self.resultado.setText(f"<span style='color:{COR_SUAVE}'>" + tr("Nenhuma entrega pendente nos contratos ativos. "
                                   "Aceite contratos de transporte no jogo e eles aparecem aqui.") + "</span>")

    def _guardar_escolhas(self) -> None:
        for p in self.paradas:
            self._escolhas[self._chave(p)] = (p.incluir, p.local)

    def _ao_marcar(self, item: QTableWidgetItem) -> None:
        if item.column() == 0 and item.row() < len(self.paradas):
            self.paradas[item.row()].incluir = item.checkState() == Qt.Checked

    def _ao_escolher_local(self, linha: int) -> None:
        if linha < len(self.paradas):
            combo = self._combos[linha]
            local = combo.currentData() if combo.currentIndex() >= 0 else None
            self.paradas[linha].local = local
            combo.setStyleSheet("" if local else f"QComboBox {{ border: 1px solid {COR_ALERTA}; }}")

    # ------------------------------------------------------------ cálculo
    def calcular(self) -> None:
        self._guardar_escolhas()
        if not any(p.incluir and p.local for p in self.paradas):
            self.resultado.setText(f"<span style='color:{COR_ALERTA}'>{tr('Defina o local de pelo menos uma parada.')}</span>")
            return
        if self.c.calcular_rota(list(self.paradas), self.inicio.currentData()):
            self.botao_calcular.setEnabled(False)
            self.resultado.setText(f"<span style='color:{COR_SUAVE}'>{tr('Calculando (buscando distâncias na UEX)…')}</span>")

    def _ao_rota(self, resultado) -> None:
        self.botao_calcular.setEnabled(True)
        if isinstance(resultado, Exception):
            self.resultado.setText(f"<span style='color:#ff5c5c'>{tr('Não foi possível calcular: {erro}', erro=html.escape(str(resultado)))}</span>")
            return
        self.resultado.setText(html_rota(resultado))
