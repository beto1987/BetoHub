"""Aba principal do Comércio: formulário à esquerda, tabela de rotas à direita."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QCompleter, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSpinBox, QSplitter,
    QTableView, QVBoxLayout, QWidget,
)

from beto_hub.ui.theme import repolir

from ..logica.modelos import ParametrosBusca, Rota
from ..logica.rotas import ORDENACOES
from .modelo_tabela import COL, PAPEL_ORDENACAO, PAPEL_ROTA, ModeloRotas

if TYPE_CHECKING:
    from ..controlador import ControladorComercio

# Como cada opção de "Ordenar por" vira ordenação de coluna da tabela
ORDEM_TABELA = {
    "eficiencia": (COL["Eficiência (aUEC/Gm)"], Qt.DescendingOrder),
    "lucro": (COL["Lucro"], Qt.DescendingOrder),
    "risco_menor": (COL["Risco"], Qt.AscendingOrder),
    "risco_maior": (COL["Risco"], Qt.DescendingOrder),
    "distancia": (COL["Distância (Gm)"], Qt.AscendingOrder),
}


def _combo_pesquisavel(combo: QComboBox) -> None:
    """Permite digitar para filtrar (ex.: "cat" encontra "Caterpillar")."""
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    completer = combo.completer()
    completer.setFilterMode(Qt.MatchContains)
    completer.setCompletionMode(QCompleter.PopupCompletion)
    completer.setCaseSensitivity(Qt.CaseInsensitive)


class AbaComercio(QWidget):
    def __init__(self, controlador: "ControladorComercio", publicar_log, parent=None):
        super().__init__(parent)
        self.c = controlador
        self._publicar_log = publicar_log  # callback(rota) -> envia ao Log do Capitão
        self._carregando_form = False

        divisor = QSplitter(Qt.Horizontal)
        divisor.addWidget(self._criar_formulario())
        divisor.addWidget(self._criar_resultados())
        divisor.setStretchFactor(1, 1)
        divisor.setSizes([320, 900])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(divisor)

        self.c.dadosAtualizados.connect(self._ao_dados)
        self.c.rotasCalculadas.connect(self._ao_rotas)
        self.c.status.connect(self._ao_status)
        self.c.ocupado.connect(self._ao_ocupado)

        if self.c.precos:
            self._ao_dados()
        if self.c.rotas:
            self._ao_rotas(self.c.rotas)

    # ================================================================ montagem
    def _criar_formulario(self) -> QWidget:
        painel = QWidget()
        painel.setMinimumWidth(290)
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(0, 0, 6, 0)

        # ---- carga e capital
        grupo = QGroupBox("CARGA E CAPITAL")
        form = QFormLayout(grupo)
        self.nave = QComboBox()
        _combo_pesquisavel(self.nave)
        self.nave.setToolTip("Escolha a nave para preencher o SCU, ou digite o SCU à mão.")
        self.nave.currentIndexChanged.connect(self._ao_escolher_nave)
        form.addRow("Nave:", self.nave)

        self.scu = QSpinBox()
        self.scu.setRange(1, 100_000)
        self.scu.setSuffix(" SCU")
        self.scu.setValue(int(self.c.opcao("scu")))
        form.addRow("Carga:", self.scu)

        self.capital = QDoubleSpinBox()
        self.capital.setDecimals(0)
        self.capital.setRange(1, 1e12)
        self.capital.setGroupSeparatorShown(True)
        self.capital.setSuffix(" aUEC")
        self.capital.setSingleStep(10_000)
        self.capital.setValue(float(self.c.opcao("capital")))
        form.addRow("Capital:", self.capital)
        layout.addWidget(grupo)

        # ---- filtros
        grupo = QGroupBox("FILTROS")
        form = QFormLayout(grupo)
        self.sistema = QComboBox()
        self.sistema.currentIndexChanged.connect(self._ao_mudar_sistema)
        form.addRow("Sistema:", self.sistema)

        self.origem = QComboBox()
        _combo_pesquisavel(self.origem)
        self.origem.setToolTip("Terminal onde você está agora (onde vai comprar).")
        form.addRow("Onde estou:", self.origem)

        self.entre_sistemas = QCheckBox("Incluir rotas entre sistemas")
        self.entre_sistemas.setChecked(bool(self.c.opcao("entre_sistemas")))
        form.addRow("", self.entre_sistemas)
        self.ignorar_jogadores = QCheckBox("Ignorar terminais de jogadores")
        self.ignorar_jogadores.setChecked(bool(self.c.opcao("ignorar_jogadores")))
        form.addRow("", self.ignorar_jogadores)
        layout.addWidget(grupo)

        # ---- ações
        self.botao_buscar = QPushButton("BUSCAR ROTAS")
        self.botao_buscar.setProperty("destaque", "true")
        self.botao_buscar.clicked.connect(self.buscar)
        self.botao_atualizar = QPushButton("Atualizar preços")
        self.botao_atualizar.setToolTip("Baixa os preços mais recentes da UEX agora.")
        self.botao_atualizar.clicked.connect(lambda: self.c.carregar_dados(forcar=True))
        layout.addWidget(self.botao_buscar)
        layout.addWidget(self.botao_atualizar)

        self.rotulo_status = QLabel("Carregando dados da UEX…")
        self.rotulo_status.setWordWrap(True)
        self.rotulo_status.setProperty("papel", "ajuda")
        layout.addWidget(self.rotulo_status)
        layout.addStretch(1)

        ajuda = QLabel(
            "Eficiência = lucro ÷ distância (Gm). Passe o mouse sobre o risco para ver os motivos "
            "e sobre origem/destino para ver o local completo. Preços: comunidade UEX Corp."
        )
        ajuda.setWordWrap(True)
        ajuda.setProperty("papel", "ajuda")
        layout.addWidget(ajuda)
        return painel

    def _criar_resultados(self) -> QWidget:
        painel = QWidget()
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(6, 0, 0, 0)

        topo = QHBoxLayout()
        topo.addWidget(QLabel("Ordenar por:"))
        self.ordenacao = QComboBox()
        for chave, (rotulo, _f, _d) in ORDENACOES.items():
            self.ordenacao.addItem(rotulo, chave)
        indice = self.ordenacao.findData(self.c.opcao("ordenacao"))
        self.ordenacao.setCurrentIndex(max(0, indice))
        self.ordenacao.currentIndexChanged.connect(self._ao_mudar_ordenacao)
        topo.addWidget(self.ordenacao)
        topo.addStretch(1)
        self.rotulo_total = QLabel("")
        self.rotulo_total.setProperty("papel", "ajuda")
        topo.addWidget(self.rotulo_total)
        layout.addLayout(topo)

        self.modelo = ModeloRotas(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.modelo)
        self.proxy.setSortRole(PAPEL_ORDENACAO)

        self.tabela = QTableView()
        self.tabela.setModel(self.proxy)
        self.tabela.setSortingEnabled(True)  # clique no cabeçalho alterna maior/menor
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.verticalHeader().setDefaultSectionSize(26)
        cab = self.tabela.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(COL["Mercadoria"], QHeaderView.Stretch)
        self.tabela.doubleClicked.connect(lambda *_: self._registrar_no_log())
        self.tabela.selectionModel().selectionChanged.connect(self._ao_selecionar)
        layout.addWidget(self.tabela, 1)

        baixo = QHBoxLayout()
        dica = QLabel("Clique no título de uma coluna para ordenar (de novo para inverter).")
        dica.setProperty("papel", "ajuda")
        baixo.addWidget(dica)
        baixo.addStretch(1)
        self.botao_log = QPushButton("Registrar no Log do Capitão")
        self.botao_log.setEnabled(False)
        self.botao_log.setToolTip("Abre o Log do Capitão com esta viagem pré-preenchida (ou dê dois cliques na rota).")
        self.botao_log.clicked.connect(self._registrar_no_log)
        baixo.addWidget(self.botao_log)
        layout.addLayout(baixo)
        return painel

    # ================================================================ dados
    def _ao_dados(self) -> None:
        """Preenche naves, sistemas e terminais quando os dados da UEX chegam."""
        self._carregando_form = True
        try:
            nave_atual = self.nave.currentData() or int(self.c.opcao("nave_id") or 0)
            self.nave.clear()
            self.nave.addItem("— digitar SCU à mão —", 0)
            for n in self.c.naves:
                self.nave.addItem(n.rotulo, n.id)
            self.nave.setCurrentIndex(max(0, self.nave.findData(nave_atual)))

            sistema_atual = self.sistema.currentData()
            if sistema_atual is None:
                sistema_atual = str(self.c.opcao("sistema"))
            self.sistema.clear()
            self.sistema.addItem("Todos os sistemas", "")
            for nome in self.c.sistemas():
                self.sistema.addItem(nome, nome)
            self.sistema.setCurrentIndex(max(0, self.sistema.findData(sistema_atual)))
            self._preencher_origens(int(self.c.opcao("origem_id") or 0))
        finally:
            self._carregando_form = False

    def _preencher_origens(self, manter_id: int | None = None) -> None:
        atual = manter_id if manter_id is not None else (self.origem.currentData() or 0)
        self.origem.clear()
        self.origem.addItem("Qualquer terminal", 0)
        for t in self.c.terminais_do_sistema(self.sistema.currentData() or ""):
            self.origem.addItem(t.rotulo, t.id)
            self.origem.setItemData(self.origem.count() - 1, t.descricao, Qt.ToolTipRole)
        self.origem.setCurrentIndex(max(0, self.origem.findData(atual)))

    def _ao_mudar_sistema(self) -> None:
        if not self._carregando_form:
            self._preencher_origens()

    def _ao_escolher_nave(self) -> None:
        if self._carregando_form:
            return
        id_nave = self.nave.currentData()
        nave = next((n for n in self.c.naves if n.id == id_nave), None)
        if nave:
            self.scu.setValue(nave.scu)

    # ================================================================ busca
    def _parametros(self) -> ParametrosBusca:
        return ParametrosBusca(
            scu=self.scu.value(),
            capital=self.capital.value(),
            sistema=self.sistema.currentData() or "",
            id_origem=self.origem.currentData() or None,
            entre_sistemas=self.entre_sistemas.isChecked(),
            ignorar_jogadores=self.ignorar_jogadores.isChecked(),
        )

    def buscar(self) -> None:
        p = self._parametros()
        self.c.ctx.salvar_opcoes({
            "nave_id": self.nave.currentData() or 0, "scu": p.scu, "capital": p.capital,
            "sistema": p.sistema, "origem_id": p.id_origem or 0,
            "entre_sistemas": p.entre_sistemas, "ignorar_jogadores": p.ignorar_jogadores,
        })
        self.c.buscar(p)

    def _ao_rotas(self, rotas: list[Rota]) -> None:
        self.modelo.definir_rotas(rotas)
        self._aplicar_ordenacao_tabela()
        lucro_max = max((r.lucro for r in rotas), default=0)
        self.rotulo_total.setText(f"{len(rotas)} rotas · maior lucro {lucro_max:,.0f} aUEC".replace(",", "."))
        self.botao_log.setEnabled(False)

    def _ao_mudar_ordenacao(self) -> None:
        self.c.reordenar(self.ordenacao.currentData())

    def _aplicar_ordenacao_tabela(self) -> None:
        coluna, ordem = ORDEM_TABELA.get(self.ordenacao.currentData(), ORDEM_TABELA["eficiencia"])
        self.tabela.sortByColumn(coluna, ordem)

    # ================================================================ estado
    def _ao_status(self, texto: str, papel: str) -> None:
        self.rotulo_status.setText(texto)
        self.rotulo_status.setProperty("papel", papel)
        repolir(self.rotulo_status)

    def _ao_ocupado(self, ocupado: bool) -> None:
        self.botao_buscar.setEnabled(not ocupado)
        self.botao_atualizar.setEnabled(not ocupado)
        self.setCursor(Qt.BusyCursor if ocupado else Qt.ArrowCursor)

    def _rota_selecionada(self) -> Rota | None:
        indices = self.tabela.selectionModel().selectedRows()
        return indices[0].data(PAPEL_ROTA) if indices else None

    def _ao_selecionar(self, *_args) -> None:
        self.botao_log.setEnabled(self._rota_selecionada() is not None)

    def _registrar_no_log(self) -> None:
        rota = self._rota_selecionada()
        if rota:
            self._publicar_log(rota)
