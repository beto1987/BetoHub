"""Interface do Log do Capitão: resumo, filtro por período, tabela e formulário."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QDateTime, QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QTableView, QVBoxLayout, QWidget,
)

from .repositorio import (
    FORMATO_DATA, NOMES_TIPO, PERIODOS, TIPO_ANOTACAO, TIPO_COMERCIO, TIPO_CONTRATO, TIPO_REFINO, Entrada,
    RepositorioLog, data_inicial,
)

FORMATO_QT = "yyyy-MM-dd HH:mm"


def _n(v: float, casas: int = 0) -> str:
    texto = f"{v:,.{casas}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


# ====================================================================== tabela
COLUNAS = ["Data", "Tipo", "Mercadoria / Título", "Rota", "SCU", "Compra/SCU", "Venda/SCU", "Investimento",
           "Lucro", "Notas"]


class ModeloLog(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entradas: list[Entrada] = []

    def definir(self, entradas: list[Entrada]) -> None:
        self.beginResetModel()
        self.entradas = entradas
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.entradas)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(COLUNAS)

    def headerData(self, secao, orientacao, papel=Qt.DisplayRole):  # noqa: N802
        if orientacao == Qt.Horizontal and papel == Qt.DisplayRole:
            return COLUNAS[secao]
        return None

    def data(self, indice, papel=Qt.DisplayRole):
        if not indice.isValid():
            return None
        e = self.entradas[indice.row()]
        col = COLUNAS[indice.column()]
        comercio = e.tem_valor  # comércio, refino ou contrato
        por_scu = e.tipo in (TIPO_COMERCIO, TIPO_REFINO)
        if papel == Qt.DisplayRole:
            if comercio and e.origem and e.destino:
                rota = f"{e.origem} → {e.destino}"
            else:
                rota = e.origem or e.destino if comercio else ""
            return {
                "Data": e.data,
                "Tipo": NOMES_TIPO.get(e.tipo, e.tipo),
                "Mercadoria / Título": e.resumo,
                "Rota": rota,
                "SCU": _n(e.scu, 2 if e.tipo == TIPO_REFINO else 0) if por_scu else "",
                "Compra/SCU": _n(e.preco_compra, 2) if e.tipo == TIPO_COMERCIO else "",
                "Venda/SCU": _n(e.preco_venda, 2) if por_scu else "",
                "Investimento": _n(e.investimento) if comercio else "",
                "Lucro": _n(e.lucro) if comercio else "",
                "Notas": e.notas.replace("\n", " ")[:80],
            }[col]
        if papel == Qt.TextAlignmentRole and col in ("SCU", "Compra/SCU", "Venda/SCU", "Investimento", "Lucro"):
            return Qt.AlignRight | Qt.AlignVCenter
        if papel == Qt.ForegroundRole and col == "Lucro" and comercio:
            return QColor("#4cd98a" if e.lucro >= 0 else "#ff5c5c")
        if papel == Qt.ToolTipRole and col == "Notas" and e.notas:
            return e.notas
        if papel == Qt.ToolTipRole and col == "Investimento" and e.tipo == TIPO_REFINO:
            return "Custo do refino"
        if papel == Qt.ToolTipRole and col in ("Investimento", "Lucro") and e.tipo == TIPO_CONTRATO:
            return f"Recompensa {_n(e.receita)} aUEC − despesas {_n(e.investimento)} aUEC"
        return None


# ====================================================================== formulário
class DialogoEntrada(QDialog):
    def __init__(self, entrada: Entrada, parent=None):
        super().__init__(parent)
        self.entrada = entrada
        comercio = entrada.tipo == TIPO_COMERCIO
        refino = entrada.tipo == TIPO_REFINO
        contrato = entrada.tipo == TIPO_CONTRATO
        novo = entrada.id is None
        nome_tipo = ("viagem" if comercio else "operação de refino" if refino else
                     "entrada de contrato" if contrato else "anotação")
        self.setWindowTitle(("Nova " if novo else "Editar ") + nome_tipo)
        self.setMinimumWidth(460)
        form = QFormLayout()

        self.data = QDateTimeEdit(QDateTime.fromString(entrada.data, FORMATO_QT))
        self.data.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.data.setCalendarPopup(True)
        form.addRow("Data e hora:", self.data)

        if comercio:
            self.mercadoria = QLineEdit(entrada.mercadoria)
            self.origem = QLineEdit(entrada.origem)
            self.destino = QLineEdit(entrada.destino)
            self.scu = self._numero(entrada.scu, 0, " SCU")
            self.compra = self._numero(entrada.preco_compra, 2, " aUEC/SCU")
            self.venda = self._numero(entrada.preco_venda, 2, " aUEC/SCU")
            form.addRow("Mercadoria:", self.mercadoria)
            form.addRow("Origem:", self.origem)
            form.addRow("Destino:", self.destino)
            form.addRow("Quantidade:", self.scu)
            form.addRow("Preço pago:", self.compra)
            form.addRow("Preço recebido:", self.venda)
            self.calculo = QLabel()
            form.addRow("Resultado:", self.calculo)
            for campo in (self.scu, self.compra, self.venda):
                campo.valueChanged.connect(self._recalcular)
            self._recalcular()
            dica = QLabel("Os valores vêm da rota escolhida; ajuste para o que você realmente pagou e recebeu.")
            dica.setWordWrap(True)
            dica.setProperty("papel", "ajuda")
            form.addRow(dica)
        elif refino:
            self.mercadoria = QLineEdit(entrada.mercadoria)
            self.origem = QLineEdit(entrada.origem)
            self.destino = QLineEdit(entrada.destino)
            self.destino.setPlaceholderText("onde vendeu o refinado")
            self.scu = self._numero(entrada.scu, 2, " SCU")
            self.compra = None
            self.custo_refino = self._numero(entrada.custo_extra, 0, " aUEC")
            self.venda = self._numero(entrada.preco_venda, 2, " aUEC/SCU")
            form.addRow("Minério(s):", self.mercadoria)
            form.addRow("Refinaria:", self.origem)
            form.addRow("Vendido em:", self.destino)
            form.addRow("Refinado:", self.scu)
            form.addRow("Custo do refino:", self.custo_refino)
            form.addRow("Preço de venda:", self.venda)
            self.calculo = QLabel()
            form.addRow("Resultado:", self.calculo)
            for campo in (self.scu, self.custo_refino, self.venda):
                campo.valueChanged.connect(self._recalcular)
            self._recalcular()
            dica = QLabel("Valores estimados pelo módulo Refino; ajuste para o que você realmente recebeu.")
            dica.setWordWrap(True)
            dica.setProperty("papel", "ajuda")
            form.addRow(dica)
        elif contrato:
            self.titulo = QLineEdit(entrada.titulo)
            self.titulo.setPlaceholderText("Nome do contrato")
            self.origem = QLineEdit(entrada.origem)
            self.origem.setPlaceholderText("Opcional. Ex.: Canard View")
            self.venda = self._numero(entrada.preco_venda, 0, " aUEC")
            self.custo_contrato = self._numero(entrada.custo_extra, 0, " aUEC")
            self.custo_contrato.setToolTip("Gastos para cumprir o contrato: combustível, munição, reparos, compra de carga…")
            form.addRow("Contrato:", self.titulo)
            form.addRow("Local:", self.origem)
            form.addRow("Recompensa:", self.venda)
            form.addRow("Despesas:", self.custo_contrato)
            self.calculo = QLabel()
            form.addRow("Resultado:", self.calculo)
            for campo in (self.venda, self.custo_contrato):
                campo.valueChanged.connect(self._recalcular)
            self._recalcular()
        else:
            self.titulo = QLineEdit(entrada.titulo)
            self.titulo.setPlaceholderText("Ex.: Emboscada perto de CRU-L1")
            form.addRow("Título:", self.titulo)

        self.notas = QPlainTextEdit(entrada.notas)
        self.notas.setPlaceholderText("Anotações livres…")
        self.notas.setFixedHeight(110 if (comercio or refino or contrato) else 180)
        form.addRow("Notas:", self.notas)

        botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Save).setText("Salvar")
        botoes.button(QDialogButtonBox.Save).setProperty("destaque", "true")
        botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botoes.accepted.connect(self._salvar)
        botoes.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(botoes)

    @staticmethod
    def _numero(valor: float, casas: int, sufixo: str) -> QDoubleSpinBox:
        campo = QDoubleSpinBox()
        campo.setDecimals(casas)
        campo.setRange(0, 1e12)
        campo.setGroupSeparatorShown(True)
        campo.setSuffix(sufixo)
        campo.setValue(float(valor or 0))
        return campo

    def _recalcular(self) -> None:
        if self.entrada.tipo == TIPO_CONTRATO:
            inv, rec = self.custo_contrato.value(), self.venda.value()
        elif self.entrada.tipo == TIPO_REFINO:
            inv = self.custo_refino.value()
            rec = self.scu.value() * self.venda.value()
        else:
            inv = self.scu.value() * self.compra.value()
            rec = self.scu.value() * self.venda.value()
        lucro = rec - inv
        cor = "#4cd98a" if lucro >= 0 else "#ff5c5c"
        self.calculo.setText(
            f"investimento {_n(inv)} · receita {_n(rec)} · "
            f"<b style='color:{cor}'>lucro {_n(lucro)} aUEC</b>"
        )

    def _salvar(self) -> None:
        e = self.entrada
        e.data = self.data.dateTime().toString(FORMATO_QT)
        e.notas = self.notas.toPlainText().strip()
        if e.tipo == TIPO_CONTRATO:
            e.titulo, e.origem = self.titulo.text().strip(), self.origem.text().strip()
            e.preco_venda, e.custo_extra, e.scu = self.venda.value(), self.custo_contrato.value(), 0
            if not e.titulo:
                QMessageBox.warning(self, "Log do Capitão", "Informe o nome do contrato.")
                return
        elif e.tem_valor:
            e.mercadoria = self.mercadoria.text().strip()
            e.origem, e.destino = self.origem.text().strip(), self.destino.text().strip()
            e.scu, e.preco_venda = self.scu.value(), self.venda.value()
            if e.tipo == TIPO_COMERCIO:
                e.preco_compra = self.compra.value()
            else:
                e.custo_extra = self.custo_refino.value()
            if not e.mercadoria or e.scu <= 0:
                QMessageBox.warning(self, "Log do Capitão", "Informe a mercadoria e a quantidade (SCU).")
                return
        else:
            e.titulo = self.titulo.text().strip()
            if not e.titulo and not e.notas:
                QMessageBox.warning(self, "Log do Capitão", "Escreva um título ou uma nota.")
                return
        self.accept()


# ====================================================================== aba
class AbaLog(QWidget):
    def __init__(self, repo: RepositorioLog, log, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.log = log

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # ---- cartões de resumo
        grade = QGridLayout()
        self.cartoes: dict[str, QLabel] = {}
        for i, (chave, titulo) in enumerate((("operacoes", "OPERAÇÕES"), ("lucro_total", "LUCRO TOTAL"),
                                             ("lucro_medio", "LUCRO MÉDIO / OPERAÇÃO"), ("melhor", "MELHOR OPERAÇÃO"))):
            cartao = QFrame()
            cartao.setStyleSheet("QFrame { border: 1px solid #1e3a52; background: #0d1520; }")
            interno = QVBoxLayout(cartao)
            rotulo = QLabel(titulo)
            rotulo.setProperty("papel", "ajuda")
            rotulo.setStyleSheet("border: none;")
            valor = QLabel("—")
            valor.setStyleSheet("border: none; font-size: 15pt; color: #35c8f5;")
            valor.setTextFormat(Qt.RichText)
            interno.addWidget(rotulo)
            interno.addWidget(valor)
            grade.addWidget(cartao, 0, i)
            self.cartoes[chave] = valor
        layout.addLayout(grade)

        # ---- barra de ações
        barra = QHBoxLayout()
        barra.addWidget(QLabel("Período:"))
        self.periodo = QComboBox()
        for rotulo in PERIODOS:
            self.periodo.addItem(rotulo)
        self.periodo.setCurrentText("Últimos 30 dias")
        self.periodo.currentIndexChanged.connect(self.recarregar)
        barra.addWidget(self.periodo)
        barra.addStretch(1)
        acoes = (
            ("+ Nova viagem", lambda: self.nova(TIPO_COMERCIO), True),
            ("+ Novo refino", lambda: self.nova(TIPO_REFINO), False),
            ("+ Novo contrato", lambda: self.nova(TIPO_CONTRATO), False),
            ("+ Nova anotação", lambda: self.nova(TIPO_ANOTACAO), False),
            ("Editar", self.editar, False),
            ("Excluir", self.excluir, False),
            ("Exportar CSV", self.exportar, False),
        )
        self.botoes: dict[str, QPushButton] = {}
        for texto, funcao, destaque in acoes:
            b = QPushButton(texto)
            if destaque:
                b.setProperty("destaque", "true")
            if texto == "Excluir":
                b.setProperty("perigo", "true")
            b.clicked.connect(lambda *_, f=funcao: f())
            barra.addWidget(b)
            self.botoes[texto] = b
        layout.addLayout(barra)

        # ---- tabela
        self.modelo = ModeloLog(self)
        self.tabela = QTableView()
        self.tabela.setModel(self.modelo)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.verticalHeader().setVisible(False)
        cab = self.tabela.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(COLUNAS.index("Notas"), QHeaderView.Stretch)
        self.tabela.doubleClicked.connect(lambda *_: self.editar())
        self.tabela.selectionModel().selectionChanged.connect(self._ao_selecionar)
        layout.addWidget(self.tabela, 1)

        self.recarregar()

    # ------------------------------------------------------------ dados
    def recarregar(self) -> None:
        try:
            entradas = self.repo.listar(data_inicial(PERIODOS[self.periodo.currentText()]))
        except Exception:
            self.log.exception("Erro ao ler o Log do Capitão")
            QMessageBox.critical(self, "Log do Capitão", "Não foi possível ler o log. Veja o arquivo de log.")
            return
        self.modelo.definir(entradas)
        r = self.repo.resumo(entradas)
        cor = "#4cd98a" if r["lucro_total"] >= 0 else "#ff5c5c"
        self.cartoes["operacoes"].setText(
            f"{r['operacoes']}  <span style='font-size:9pt;color:#7f98ad'>"
            f"{r['viagens']} viagens · {r['refinos']} refinos · {r['contratos']} contratos</span>")
        self.cartoes["lucro_total"].setText(f"<span style='color:{cor}'>{_n(r['lucro_total'])}</span>")
        self.cartoes["lucro_medio"].setText(_n(r["lucro_medio"]))
        m = r["melhor"]
        self.cartoes["melhor"].setText(
            f"{_n(m.lucro)} <span style='font-size:9pt;color:#7f98ad'>{m.resumo}</span>" if m else "—"
        )
        self._ao_selecionar()

    def _selecionada(self) -> Entrada | None:
        linhas = self.tabela.selectionModel().selectedRows()
        return self.modelo.entradas[linhas[0].row()] if linhas else None

    def _ao_selecionar(self, *_a) -> None:
        tem = self._selecionada() is not None
        self.botoes["Editar"].setEnabled(tem)
        self.botoes["Excluir"].setEnabled(tem)

    # ------------------------------------------------------------ ações
    def nova(self, tipo: str, dados: dict[str, Any] | None = None) -> None:
        entrada = Entrada(tipo=tipo, data=datetime.now().strftime(FORMATO_DATA))
        for chave, valor in (dados or {}).items():
            if hasattr(entrada, chave):
                setattr(entrada, chave, valor)
        self._abrir(entrada)

    def editar(self) -> None:
        e = self._selecionada()
        if e:
            self._abrir(Entrada(**{k: getattr(e, k) for k in e.__dataclass_fields__}))

    def _abrir(self, entrada: Entrada) -> None:
        if DialogoEntrada(entrada, self).exec() != QDialog.Accepted:
            return
        try:
            self.repo.salvar(entrada)
        except Exception:
            self.log.exception("Erro ao salvar entrada do Log do Capitão")
            QMessageBox.critical(self, "Log do Capitão", "Não foi possível salvar. Veja o arquivo de log.")
            return
        self.log.info("Log do Capitão: entrada %s salva (%s)", entrada.id, entrada.resumo)
        self.recarregar()

    def excluir(self) -> None:
        e = self._selecionada()
        if not e:
            return
        resposta = QMessageBox.question(
            self, "Excluir entrada",
            f"Excluir \"{e.resumo}\" de {e.data}?\nEssa ação não pode ser desfeita.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if resposta == QMessageBox.Yes:
            self.repo.excluir(e.id)
            self.log.info("Log do Capitão: entrada %s excluída", e.id)
            self.recarregar()

    def exportar(self) -> None:
        nome = f"log_do_capitao_{datetime.now():%Y-%m-%d}.csv"
        caminho, _ = QFileDialog.getSaveFileName(self, "Exportar Log do Capitão", str(Path.home() / nome),
                                                 "Planilha CSV (*.csv)")
        if not caminho:
            return
        try:
            self.repo.exportar_csv(self.modelo.entradas, Path(caminho))
        except OSError as erro:
            QMessageBox.critical(self, "Exportar", f"Não foi possível salvar o arquivo:\n{erro}")
            return
        QMessageBox.information(self, "Exportar", f"{len(self.modelo.entradas)} entradas exportadas para:\n{caminho}")
