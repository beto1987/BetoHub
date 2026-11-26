"""Aba principal da Mineração no Hub."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QIntValidator, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from beto_hub.ui.theme import repolir

from .editor_nave import EditorNave
from .render import html_completo, html_leitura
from .selecao import SeletorArea

if TYPE_CHECKING:
    from ..controlador import ControladorMineracao

TEXTOS_AREA = {
    "regiao_numero": "Arraste um retângulo em volta de onde aparece o NÚMERO do scan  |  Esc cancela",
    "regiao_rocha": "Arraste um retângulo em volta do painel da rocha (MASS / RESISTANCE / INSTABILITY)  |  Esc cancela",
}


def pil_para_pixmap(img) -> QPixmap:
    rgb = img.convert("RGB")
    dados = rgb.tobytes("raw", "RGB")
    qimg = QImage(dados, rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())  # copy: o QImage não pode depender do buffer Python


def _ajuda(texto: str) -> QLabel:
    r = QLabel(texto)
    r.setWordWrap(True)
    r.setProperty("papel", "ajuda")
    return r


class AbaMineracao(QWidget):
    def __init__(self, c: "ControladorMineracao", parent=None):
        super().__init__(parent)
        self.c = c
        self.seletor = SeletorArea(self)
        self.seletor.concluido.connect(self._ao_selecionar_area)
        self._area_em_selecao: str | None = None

        divisor = QSplitter(Qt.Horizontal)
        divisor.addWidget(self._painel_esquerdo())
        divisor.addWidget(self._painel_direito())
        divisor.setStretchFactor(1, 1)
        divisor.setSizes([380, 820])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(divisor)

        c.ativoAlterado.connect(self._ao_ativo)
        c.status.connect(self._ao_status)
        c.leituraNova.connect(self._atualizar_leituras)
        c.rochaNova.connect(self._atualizar_leituras)
        c.refinoAtualizado.connect(self._atualizar_leituras)
        c.opcoesAlteradas.connect(self._atualizar_areas)
        c.loadoutTrocado.connect(lambda: self.editor.definir(self.c.loadout))
        self._ao_ativo(c.ativo)
        self._ao_status(*c.ultimo_status)
        self._atualizar_areas()
        self._atualizar_leituras()

    # ================================================================ esquerda
    def _painel_esquerdo(self) -> QWidget:
        interno = QWidget()
        layout = QVBoxLayout(interno)
        layout.setContentsMargins(0, 0, 6, 0)

        # ---- controle
        g = QGroupBox("SCANNER")
        v = QVBoxLayout(g)
        self.botao_ativo = QPushButton()
        self.botao_ativo.setMinimumHeight(36)
        self.botao_ativo.clicked.connect(self.c.alternar)
        v.addWidget(self.botao_ativo)
        self.rotulo_status = QLabel()
        self.rotulo_status.setWordWrap(True)
        v.addWidget(self.rotulo_status)
        self.so_com_jogo = QCheckBox("Só ler com o Star Citizen em primeiro plano")
        self.so_com_jogo.setChecked(bool(self.c.opcoes["so_com_jogo"]))
        self.so_com_jogo.toggled.connect(lambda v: self.c.atualizar_opcoes({"so_com_jogo": v}))
        v.addWidget(self.so_com_jogo)
        layout.addWidget(g)

        # ---- áreas
        g = QGroupBox("ÁREAS DA TELA")
        form = QFormLayout(g)
        self.rotulos_area: dict[str, QLabel] = {}
        for chave, titulo in (("regiao_numero", "Número do scan"), ("regiao_rocha", "Painel da rocha")):
            rot = QLabel()
            rot.setProperty("papel", "ajuda")
            self.rotulos_area[chave] = rot
            agora = QPushButton("Marcar agora")
            agora.clicked.connect(lambda *_, k=chave: self._selecionar(k, 0))
            em5 = QPushButton("Em 5 s")
            em5.setToolTip("Dá 5 segundos para você voltar ao jogo e pingar antes do print.")
            em5.clicked.connect(lambda *_, k=chave: self._selecionar(k, 5))
            linha = QHBoxLayout()
            linha.addWidget(agora)
            linha.addWidget(em5)
            if chave == "regiao_rocha":
                remover = QPushButton("Remover")
                remover.setProperty("perigo", "true")
                remover.clicked.connect(lambda: self.c.atualizar_opcoes({"regiao_rocha": {}}))
                linha.addWidget(remover)
            caixa = QVBoxLayout()
            caixa.addLayout(linha)
            caixa.addWidget(rot)
            form.addRow(f"{titulo}:", caixa)
        self.contagem = QLabel()
        self.contagem.setProperty("papel", "alerta")
        form.addRow(self.contagem)
        self.seletor.contagem.connect(lambda s: self.contagem.setText(f"Print em {s} s… vá para o jogo e pingue."))
        layout.addWidget(g)

        # ---- nave
        g = QGroupBox("NAVE E LASERS")
        v = QVBoxLayout(g)
        self.editor = EditorNave(self.c.dados, self.c.loadout)
        self.editor.alterado.connect(self.c.salvar_loadout)
        v.addWidget(self.editor)
        layout.addWidget(g)

        # ---- ajustes de OCR
        g = QGroupBox("AJUSTES DO OCR")
        form = QFormLayout(g)
        op = self.c.opcoes
        self.motor = QComboBox()
        for rot, val in (("Automático", "auto"), ("OCR do Windows", "windows"), ("Tesseract", "tesseract")):
            self.motor.addItem(rot, val)
        self.motor.setCurrentIndex(max(0, self.motor.findData(op["motor_ocr"])))
        self.idioma = QComboBox()
        for val in ("auto", "en-US", "en-GB", "pt-BR"):
            self.idioma.addItem("Automático" if val == "auto" else val, val)
        self.idioma.setCurrentIndex(max(0, self.idioma.findData(op["idioma_ocr"])))
        self.intervalo = self._spin(100, 2000, op["intervalo_ms"], " ms", 50)
        self.escala = self._spin(1, 8, op["escala"], "×")
        self.limiar = self._spin(30, 240, op["limiar"], "", 5)
        self.texto_escuro = QCheckBox("Texto mais escuro que o fundo")
        self.texto_escuro.setChecked(bool(op["texto_escuro"]))
        self.refinarias = self._spin(1, 6, op["refinarias_mostradas"], " estações")
        form.addRow("Motor:", self.motor)
        form.addRow("Idioma:", self.idioma)
        form.addRow("Intervalo:", self.intervalo)
        form.addRow("Ampliação:", self.escala)
        form.addRow("Limiar (0–255):", self.limiar)
        form.addRow("", self.texto_escuro)
        form.addRow("Melhor refino:", self.refinarias)
        for w in (self.motor, self.idioma):
            w.currentIndexChanged.connect(self._salvar_ajustes)
        for w in (self.intervalo, self.escala, self.limiar, self.refinarias):
            w.valueChanged.connect(self._salvar_ajustes)
        self.texto_escuro.toggled.connect(self._salvar_ajustes)
        layout.addWidget(g)
        layout.addStretch(1)

        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QScrollArea.NoFrame)
        rolagem.setWidget(interno)
        rolagem.setMinimumWidth(340)
        return rolagem

    @staticmethod
    def _spin(minimo: int, maximo: int, valor, sufixo: str = "", passo: int = 1) -> QSpinBox:
        s = QSpinBox()
        s.setRange(minimo, maximo)
        s.setSingleStep(passo)
        s.setValue(int(valor))
        s.setSuffix(sufixo)
        return s

    def _salvar_ajustes(self, *_a) -> None:
        self.c.atualizar_opcoes({
            "motor_ocr": self.motor.currentData(), "idioma_ocr": self.idioma.currentData(),
            "intervalo_ms": self.intervalo.value(), "escala": self.escala.value(),
            "limiar": self.limiar.value(), "texto_escuro": self.texto_escuro.isChecked(),
            "refinarias_mostradas": self.refinarias.value(),
        })
        self._atualizar_leituras()

    # ================================================================ direita
    def _painel_direito(self) -> QWidget:
        abas = QTabWidget()
        abas.addTab(self._aba_leitura(), "LEITURA ATUAL")
        abas.addTab(self._aba_historico(), "HISTÓRICO")
        abas.addTab(self._aba_teste(), "TESTAR LEITURA")
        return abas

    def _aba_leitura(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        linha = QHBoxLayout()
        linha.addWidget(QLabel("Digitar um número:"))
        self.numero_manual = QLineEdit()
        self.numero_manual.setValidator(QIntValidator(1, 9_999_999))
        self.numero_manual.setPlaceholderText("ex.: 17080")
        self.numero_manual.returnPressed.connect(self._identificar_manual)
        linha.addWidget(self.numero_manual)
        b = QPushButton("Identificar")
        b.clicked.connect(self._identificar_manual)
        linha.addWidget(b)
        linha.addStretch(1)
        v.addLayout(linha)
        self.visor = QLabel()
        self.visor.setTextFormat(Qt.RichText)
        self.visor.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.visor.setWordWrap(True)
        self.visor.setStyleSheet("font-size: 11pt; padding: 6px;")
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setWidget(self.visor)
        v.addWidget(rolagem, 1)
        return w

    def _aba_historico(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.tabela = QTableWidget(0, 3)
        self.tabela.setHorizontalHeaderLabels(["Quando", "Assinatura", "Resultado"])
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setStretchLastSection(True)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela.currentCellChanged.connect(self._mostrar_detalhe_historico)
        v.addWidget(self.tabela, 2)
        self.detalhe = QLabel()
        self.detalhe.setTextFormat(Qt.RichText)
        self.detalhe.setWordWrap(True)
        self.detalhe.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        v.addWidget(self.detalhe, 1)
        limpar = QPushButton("Limpar histórico")
        limpar.setProperty("perigo", "true")
        limpar.clicked.connect(self._limpar_historico)
        linha = QHBoxLayout()
        linha.addStretch(1)
        linha.addWidget(limpar)
        v.addLayout(linha)
        return w

    def _aba_teste(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(_ajuda(
            "Captura a área marcada agora e mostra a imagem, o que o OCR leu em cada ajuste e o "
            "resultado. Use \"em 5 s\" para dar tempo de voltar ao jogo e pingar."
        ))
        linha = QHBoxLayout()
        for texto, tipo, atraso in (("Número agora", "regiao_numero", 0), ("Número em 5 s", "regiao_numero", 5),
                                    ("Rocha agora", "regiao_rocha", 0), ("Rocha em 5 s", "regiao_rocha", 5)):
            b = QPushButton(texto)
            b.clicked.connect(lambda *_, t=tipo, a=atraso: self._testar(t, a))
            linha.addWidget(b)
        linha.addStretch(1)
        v.addLayout(linha)
        imagens = QHBoxLayout()
        self.img_bruta, self.img_proc = QLabel("captura"), QLabel("imagem para o OCR")
        for rot in (self.img_bruta, self.img_proc):
            rot.setAlignment(Qt.AlignCenter)
            rot.setMinimumHeight(120)
            rot.setStyleSheet("border: 1px solid #1e3a52;")
            imagens.addWidget(rot)
        v.addLayout(imagens)
        self.saida_teste = QPlainTextEdit()
        self.saida_teste.setReadOnly(True)
        v.addWidget(self.saida_teste, 1)
        return w

    # ================================================================ ações
    def _selecionar(self, chave: str, atraso: int) -> None:
        if self.seletor.ativo:
            return
        self._area_em_selecao = chave
        self.seletor.iniciar(TEXTOS_AREA[chave], atraso)

    def _ao_selecionar_area(self, regiao) -> None:
        self.contagem.setText("")
        chave = self._area_em_selecao
        self._area_em_selecao = None
        if regiao and chave:
            self.c.atualizar_opcoes({chave: regiao})
            self.c.log.info("Área %s salva: %s", chave, regiao)

    def _atualizar_areas(self) -> None:
        for chave, rot in self.rotulos_area.items():
            r = self.c.opcoes.get(chave) or {}
            rot.setText(f"{r['width']}×{r['height']} px em ({r['left']}, {r['top']})"
                        if r.get("width") else "não marcada")

    def _identificar_manual(self) -> None:
        texto = self.numero_manual.text().strip()
        if texto.isdigit():
            self.c.identificar_manual(int(texto))
            self.numero_manual.clear()

    def _limpar_historico(self) -> None:
        if QMessageBox.question(self, "Mineração", "Apagar todo o histórico de leituras?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.c.limpar_historico()

    def _testar(self, chave: str, atraso: int) -> None:
        regiao = self.c.opcoes.get(chave) or {}
        if not regiao.get("width"):
            self.saida_teste.setPlainText("Essa área ainda não foi marcada.")
            return
        if atraso:
            self.saida_teste.setPlainText(f"Capturando em {atraso} s… vá para o jogo.")
            QTimer.singleShot(atraso * 1000, lambda: self._testar(chave, 0))
            return
        self.saida_teste.setPlainText("Lendo…")
        self.c.ctx.workers.executar(self.c.testar_leitura, chave,
                                    ao_concluir=self._ao_teste, ao_falhar=lambda e: self.saida_teste.setPlainText(f"Erro: {e}"))

    def _ao_teste(self, r: dict) -> None:
        self.img_bruta.setPixmap(pil_para_pixmap(r["bruta"]).scaled(
            self.img_bruta.width(), 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if r.get("processada") is not None:
            self.img_proc.setPixmap(pil_para_pixmap(r["processada"]).scaled(
                self.img_proc.width(), 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.saida_teste.setPlainText(
            f"Motor: {r['motor']}  ·  {time.strftime('%H:%M:%S')}\n\nRESULTADO: {r['resumo']}\n\n"
            + "\n".join(r["diagnostico"])
        )

    # ================================================================ estado
    def _ao_ativo(self, ativo: bool) -> None:
        self.botao_ativo.setText("⏸  PAUSAR SCANNER" if ativo else "▶  LIGAR SCANNER")
        self.botao_ativo.setProperty("destaque", "false" if ativo else "true")
        repolir(self.botao_ativo)

    def _ao_status(self, texto: str, papel: str) -> None:
        self.rotulo_status.setText(texto)
        self.rotulo_status.setProperty("papel", papel)
        repolir(self.rotulo_status)

    def _atualizar_leituras(self) -> None:
        c = self.c
        historico = c.historico(50)
        quantas_ref = int(c.opcoes["refinarias_mostradas"])
        self.visor.setText(html_completo(c.rocha, historico[:3], c.dados, c.loadout, c.refino, quantas_ref))
        self.tabela.setRowCount(len(historico))
        self._historico = historico
        for i, h in enumerate(historico):
            valores = " / ".join(f"{v:,}".replace(",", ".") for v, _ in h["results"])
            resumo = []
            for _v, cands in h["results"]:
                if cands:
                    s = cands[0]
                    resumo.append(f"{s['count']}× {s['sig']['name']}" + ("" if s.get("exact", True) else " ~"))
                else:
                    resumo.append("desconhecido")
            for j, texto in enumerate((str(h["momento"]), valores, "  |  ".join(resumo))):
                self.tabela.setItem(i, j, QTableWidgetItem(texto))

    def _mostrar_detalhe_historico(self, linha: int, *_a) -> None:
        if 0 <= linha < len(getattr(self, "_historico", [])):
            self.detalhe.setText(html_leitura(self._historico[linha]["results"], self.c.refino,
                                              int(self.c.opcoes["refinarias_mostradas"])))
