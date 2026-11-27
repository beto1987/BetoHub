"""Painel da Mineração no overlay: botão Ligar/Pausar (clicável), rocha e leituras.

O overlay não rouba o foco do jogo, então clicar no botão não tira o Star
Citizen do primeiro plano. Com "clique atravessa" ligado nada no overlay
recebe clique — desligue pelo atalho antes de usar o botão.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from beto_hub.core.i18n import tr
from beto_hub.ui.theme import repolir

from ..controlador import ControladorMineracao
from .render import html_completo, texto_nave


class PainelOverlayMineracao(QWidget):
    def __init__(self, c: ControladorMineracao, parent=None):
        super().__init__(parent)
        self.c = c
        self._pisca = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 4)
        layout.setSpacing(4)

        topo = QHBoxLayout()
        self.botao = QPushButton()
        self.botao.setCursor(Qt.PointingHandCursor)
        self.botao.setFocusPolicy(Qt.NoFocus)  # não "prende" o teclado
        self.botao.clicked.connect(c.alternar)
        topo.addWidget(self.botao)
        self.indicador = QLabel("●")
        topo.addWidget(self.indicador)
        self.status = QLabel()
        self.status.setProperty("papel", "ajuda")
        self.status.setWordWrap(True)
        topo.addWidget(self.status, 1)
        layout.addLayout(topo)

        self.visor = QLabel()
        self.visor.setTextFormat(Qt.RichText)
        self.visor.setWordWrap(True)
        self.visor.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QScrollArea.NoFrame)
        rolagem.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        rolagem.setWidget(self.visor)
        layout.addWidget(rolagem, 1)

        self.rodape = QLabel()
        self.rodape.setStyleSheet("color: #f2a93b; font-size: 8pt;")
        layout.addWidget(self.rodape)

        c.ativoAlterado.connect(self._ao_ativo)
        c.status.connect(self._ao_status)
        c.pulso.connect(self._ao_pulso)
        for sinal in (c.leituraNova, c.rochaNova, c.refinoAtualizado, c.opcoesAlteradas):
            sinal.connect(self.atualizar)
        self._ao_ativo(c.ativo)
        self._ao_status(*c.ultimo_status)
        self.atualizar()

    def _ao_ativo(self, ativo: bool) -> None:
        self.botao.setText("⏸ " + tr("PAUSAR") if ativo else "▶ " + tr("LIGAR"))
        self.botao.setProperty("destaque", "false" if ativo else "true")
        repolir(self.botao)
        self.indicador.setStyleSheet("color: #7f8a97;")

    def _ao_status(self, texto: str, papel: str) -> None:
        self.status.setText(texto)
        self.status.setProperty("papel", papel)
        repolir(self.status)
        if papel != "ok":
            self.indicador.setStyleSheet("color: #7f8a97;")

    def _ao_pulso(self) -> None:
        self._pisca = not self._pisca
        self.indicador.setStyleSheet(f"color: {'#5ad8f5' if self._pisca else '#2a6f80'};")

    def atualizar(self, *_a) -> None:
        c = self.c
        quantas = max(1, int(c.opcoes.get("leituras_no_overlay", 3)))
        self.visor.setText(html_completo(c.rocha, c.historico(quantas), c.dados, c.loadout, c.refino,
                                         int(c.opcoes["refinarias_mostradas"])))
        self.rodape.setText(texto_nave(c.loadout))
