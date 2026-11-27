"""Painel do Refino no overlay: botão de novo pedido e avisos de pedidos prontos.

Os pedidos em andamento ficam só na aba do Hub, como combinado.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from beto_hub.core.i18n import tr
from ..controlador import ControladorRefino
from ..logica.pedidos import PRONTO
from .aba import abrir_novo_pedido


class PainelOverlayRefino(QWidget):
    def __init__(self, c: ControladorRefino, parent=None):
        super().__init__(parent)
        self.c = c
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)

        botao = QPushButton(tr("+ NOVO PEDIDO DE REFINO"))
        botao.setProperty("destaque", "true")
        botao.setCursor(Qt.PointingHandCursor)
        botao.setFocusPolicy(Qt.NoFocus)
        botao.clicked.connect(lambda: abrir_novo_pedido(self.c, None))
        layout.addWidget(botao)

        dica = QLabel(tr("Abre uma janelinha por cima do jogo para registrar o pedido logo depois de "
                         "iniciá-lo no terminal de refino."))
        dica.setWordWrap(True)
        dica.setProperty("papel", "ajuda")
        layout.addWidget(dica)

        self.prontos = QLabel()
        self.prontos.setTextFormat(Qt.RichText)
        self.prontos.setWordWrap(True)
        layout.addWidget(self.prontos)
        layout.addStretch(1)

        c.pedidosAlterados.connect(self.atualizar)
        self.atualizar()

    def atualizar(self, *_a) -> None:
        prontos = [p for p in self.c.pedidos() if p.status == PRONTO]
        if not prontos:
            self.prontos.setText("")
            return
        linhas = [f"<div style='color:#4cd98a; font-weight:600;'>✔ {tr('PRONTO PARA RETIRAR')}</div>"]
        for p in prontos[:6]:
            nomes = ", ".join(i.get("nome", "?") for i in p.itens)
            linhas.append(f"<div style='color:#d6e6f2;'>▸ {nomes} <span style='color:#7f98ad'>· {p.refinaria}</span></div>")
        self.prontos.setText("".join(linhas))
