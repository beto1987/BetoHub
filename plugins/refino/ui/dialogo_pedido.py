"""Janela "Novo pedido de refino": refinaria, minérios (em cSCU), comparação de
métodos (estimativas em SCU) e confirmação com os valores do jogo.

Abre sempre por cima (inclusive pelo overlay, com o jogo em tela) e recebe o
teclado enquanto estiver aberta.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QDateTime, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QCompleter, QDateTimeEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..logica.estimativas import NOMES_NIVEL, Estimativa, Item, chave_minerio, formatar_minutos
from ..logica.pedidos import Pedido

if TYPE_CHECKING:
    from ..controlador import ControladorRefino

MAX_MINERIOS = 8


def _n(v: float | None, casas: int = 0) -> str:
    if v is None:
        return "—"
    return f"{v:,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _pontos(nota: int) -> str:
    return "●" * max(0, nota) + "○" * max(0, 3 - nota)


def _combo_pesquisavel(combo: QComboBox) -> None:
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    c = combo.completer()
    c.setFilterMode(Qt.MatchContains)
    c.setCompletionMode(QCompleter.PopupCompletion)
    c.setCaseSensitivity(Qt.CaseInsensitive)


class _LinhaMinerio(QWidget):
    def __init__(self, minerios: dict[str, str], ao_mudar, ao_remover, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.minerio = QComboBox()
        for chave, nome in minerios.items():
            self.minerio.addItem(nome, chave)
        _combo_pesquisavel(self.minerio)
        self.quantidade = QSpinBox()
        self.quantidade.setRange(0, 10_000_000)
        self.quantidade.setSingleStep(100)
        self.quantidade.setGroupSeparatorShown(True)
        self.quantidade.setSuffix(" cSCU")
        self.quantidade.setToolTip("Quantidade bruta como aparece no terminal de refino (1 SCU = 100 cSCU).")
        remover = QPushButton("✕")
        remover.setFixedWidth(32)
        remover.setToolTip("Remover este minério")
        remover.clicked.connect(lambda: ao_remover(self))
        h.addWidget(self.minerio, 2)
        h.addWidget(self.quantidade, 1)
        h.addWidget(remover)
        self.minerio.currentIndexChanged.connect(ao_mudar)
        self.quantidade.valueChanged.connect(ao_mudar)

    def item(self) -> Item | None:
        nome = self.minerio.currentText().strip()
        # sem dados da UEX a lista vem vazia: aceita o nome digitado
        chave = self.minerio.currentData() or chave_minerio(nome)
        if not chave or self.quantidade.value() <= 0:
            return None
        return Item(chave, nome, float(self.quantidade.value()))


class DialogoPedido(QDialog):
    def __init__(self, c: "ControladorRefino", parent=None):
        super().__init__(parent)
        self.c = c
        self.pedido: Pedido | None = None
        self._estimativas: list[Estimativa] = []
        self._valores_editados = False
        self.setWindowTitle("Novo pedido de refino — Beto Hub")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setMinimumSize(780, 640)

        self._recalc = QTimer(self, singleShot=True, interval=150)
        self._recalc.timeout.connect(self._recalcular)

        layout = QVBoxLayout(self)

        # ---- refinaria e minérios
        g = QGroupBox("CARGA")
        v = QVBoxLayout(g)
        form = QFormLayout()
        self.refinaria = QComboBox()
        for r in sorted(c.refinarias.values(), key=lambda r: r.rotulo.lower()):
            self.refinaria.addItem(r.rotulo, r.id_terminal)
        _combo_pesquisavel(self.refinaria)
        self.refinaria.currentIndexChanged.connect(self._agendar)
        form.addRow("Refinaria:", self.refinaria)
        v.addLayout(form)
        self.area_itens = QVBoxLayout()
        v.addLayout(self.area_itens)
        linha = QHBoxLayout()
        self.botao_mais = QPushButton("+ minério")
        self.botao_mais.clicked.connect(self._adicionar_linha)
        linha.addWidget(self.botao_mais)
        self.rotulo_bonus = QLabel()
        self.rotulo_bonus.setProperty("papel", "ajuda")
        linha.addWidget(self.rotulo_bonus, 1)
        v.addLayout(linha)
        layout.addWidget(g)

        # ---- comparação de métodos
        g = QGroupBox("COMPARAÇÃO DE MÉTODOS (ESTIMATIVA, EM SCU)")
        v = QVBoxLayout(g)
        self.tabela = QTableWidget(0, 8)
        self.tabela.setHorizontalHeaderLabels(
            ["Método", "Refinado", "Custo", "Tempo", "Valor de venda", "Lucro previsto", "Base", "Rend · Custo · Vel"])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setStretchLastSection(True)
        self.tabela.itemSelectionChanged.connect(self._ao_escolher_metodo)
        v.addWidget(self.tabela)
        nota = QLabel("Estimativas a partir de pedidos reais enviados à UEX pela comunidade; a coluna Base diz "
                      "de onde vieram e quantos relatos. Valor de venda = melhor preço do minério refinado na UEX.")
        nota.setWordWrap(True)
        nota.setProperty("papel", "ajuda")
        v.addWidget(nota)
        layout.addWidget(g, 1)

        # ---- valores do jogo
        g = QGroupBox("CONFIRME COM O TERMINAL DO JOGO")
        form = QFormLayout(g)
        self.custo = QDoubleSpinBox()
        self.custo.setDecimals(0)
        self.custo.setRange(0, 1e10)
        self.custo.setGroupSeparatorShown(True)
        self.custo.setSuffix(" aUEC")
        self.horas, self.minutos = QSpinBox(), QSpinBox()
        self.horas.setRange(0, 999)
        self.horas.setSuffix(" h")
        self.minutos.setRange(0, 59)
        self.minutos.setSuffix(" min")
        tempo = QHBoxLayout()
        tempo.addWidget(self.horas)
        tempo.addWidget(self.minutos)
        tempo.addStretch(1)
        for w in (self.custo, self.horas, self.minutos):
            w.valueChanged.connect(self._marcar_editado)
        self.inicio = QDateTimeEdit(QDateTime.currentDateTime())
        self.inicio.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.inicio.setCalendarPopup(True)
        self.inicio.setToolTip("Quando o refino começou no jogo (ajuste se estiver registrando depois).")
        self.notas = QLineEdit()
        self.notas.setPlaceholderText("opcional")
        form.addRow("Custo do refino:", self.custo)
        form.addRow("Tempo de refino:", tempo)
        form.addRow("Começou em:", self.inicio)
        form.addRow("Notas:", self.notas)
        layout.addWidget(g)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Ok).setText("Criar pedido")
        botoes.button(QDialogButtonBox.Ok).setProperty("destaque", "true")
        botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botoes.accepted.connect(self._criar)
        botoes.rejected.connect(self.reject)
        self.aviso = QLabel()
        self.aviso.setProperty("papel", "erro")
        layout.addWidget(self.aviso)
        layout.addWidget(botoes)

        self._linhas: list[_LinhaMinerio] = []
        self._adicionar_linha()
        if not c.estimador:
            self.aviso.setText("Os dados da UEX ainda não chegaram: digite refinaria e minério à mão; "
                               "o pedido é criado sem estimativas.")

    # ================================================================ minérios
    def _adicionar_linha(self) -> None:
        if len(self._linhas) >= MAX_MINERIOS:
            return
        linha = _LinhaMinerio(self.c.minerios, self._agendar, self._remover_linha)
        self._linhas.append(linha)
        self.area_itens.addWidget(linha)
        self.botao_mais.setEnabled(len(self._linhas) < MAX_MINERIOS)
        linha.quantidade.setFocus()
        self._agendar()

    def _remover_linha(self, linha: _LinhaMinerio) -> None:
        if len(self._linhas) <= 1:
            linha.quantidade.setValue(0)
            return
        self._linhas.remove(linha)
        linha.deleteLater()
        self.botao_mais.setEnabled(True)
        self._agendar()

    def _itens(self) -> list[Item]:
        return [i for i in (l.item() for l in self._linhas) if i]

    # ================================================================ estimativas
    def _agendar(self, *_a) -> None:
        self._recalc.start()

    def _recalcular(self) -> None:
        id_terminal = self.refinaria.currentData() or 0
        itens = self._itens()
        ref = self.c.refinarias.get(id_terminal)
        if ref and itens:
            partes = [f"{i.nome} {ref.bonus.get(i.chave, 0):+g}%" for i in itens]
            self.rotulo_bonus.setText("Bônus desta refinaria: " + " · ".join(partes))
        else:
            self.rotulo_bonus.setText("")

        anterior = self._metodo_escolhido()
        self._estimativas = self.c.estimar(id_terminal, itens) if itens else []
        self.tabela.setRowCount(len(self._estimativas))
        for linha, e in enumerate(self._estimativas):
            lucro_cor = None if e.lucro is None else QColor("#4cd98a" if e.lucro >= 0 else "#ff5c5c")
            celulas = [
                e.metodo.nome,
                f"{_n(e.refinado_scu, 2)} SCU" if e.refinado_scu is not None else "—",
                _n(e.custo), formatar_minutos(e.minutos), _n(e.valor), _n(e.lucro),
                f"{NOMES_NIVEL[e.nivel]} ({e.amostras})" if e.nivel != "sem dados" else "sem dados",
                f"{_pontos(e.metodo.nota_rendimento)}  {_pontos(e.metodo.nota_custo)}  {_pontos(e.metodo.nota_velocidade)}",
            ]
            for col, texto in enumerate(celulas):
                item = QTableWidgetItem(texto)
                if col in (1, 2, 4, 5):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col == 5 and lucro_cor:
                    item.setForeground(lucro_cor)
                self.tabela.setItem(linha, col, item)
        # mantém o método escolhido; senão, o de maior lucro
        nomes = [e.metodo.nome for e in self._estimativas]
        alvo = nomes.index(anterior) if anterior in nomes else (0 if nomes else -1)
        if alvo >= 0:
            self.tabela.selectRow(alvo)

    def _metodo_escolhido(self) -> str | None:
        linhas = self.tabela.selectionModel().selectedRows() if self.tabela.selectionModel() else []
        if linhas and 0 <= linhas[0].row() < len(self._estimativas):
            return self._estimativas[linhas[0].row()].metodo.nome
        return None

    def _estimativa_escolhida(self) -> Estimativa | None:
        nome = self._metodo_escolhido()
        return next((e for e in self._estimativas if e.metodo.nome == nome), None)

    def _ao_escolher_metodo(self) -> None:
        e = self._estimativa_escolhida()
        if e is None or self._valores_editados:
            return
        # pré-preenche com a estimativa até o usuário digitar os valores do jogo
        self._preenchendo = True
        self.custo.setValue(e.custo or 0)
        total = int(round(e.minutos or 0))
        self.horas.setValue(total // 60)
        self.minutos.setValue(total % 60)
        self._preenchendo = False

    def _marcar_editado(self, *_a) -> None:
        if not getattr(self, "_preenchendo", False):
            self._valores_editados = True

    # ================================================================ criar
    def _criar(self) -> None:
        itens = self._itens()
        if not itens:
            self.aviso.setText("Informe pelo menos um minério com quantidade.")
            return
        minutos = self.horas.value() * 60 + self.minutos.value()
        if minutos <= 0:
            self.aviso.setText("Informe o tempo de refino mostrado no terminal do jogo.")
            return
        e = self._estimativa_escolhida()
        por_chave = {ei.item.chave: ei for ei in (e.itens if e else [])}
        self.pedido = Pedido(
            refinaria=self.refinaria.currentText() or "?",
            id_terminal=int(self.refinaria.currentData() or 0),
            metodo=e.metodo.nome if e else "",
            minutos=float(minutos),
            custo=self.custo.value(),
            inicio=self.inicio.dateTime().toSecsSinceEpoch() or time.time(),
            itens=[{"nome": i.nome, "chave": i.chave, "quantidade_cscu": i.quantidade_cscu,
                    "refinado_scu": por_chave[i.chave].refinado_scu if i.chave in por_chave else None}
                   for i in itens],
            valor_estimado=e.valor if e else None,
            notas=self.notas.text().strip(),
        )
        self.accept()
