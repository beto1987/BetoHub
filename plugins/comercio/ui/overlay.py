"""Painel do Comércio no overlay: as 5 melhores rotas da última busca."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ..controlador import ControladorComercio, tempo_relativo
from ..logica.modelos import Rota
from ..logica.rotas import ORDENACOES
from . import formato as fmt

QUANTIDADE = 5


class PainelOverlayComercio(QWidget):
    def __init__(self, controlador: ControladorComercio, parent=None):
        super().__init__(parent)
        self.c = controlador
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        self.titulo = QLabel()
        self.titulo.setProperty("papel", "ajuda")
        layout.addWidget(self.titulo)

        self.linhas: list[QLabel] = []
        for _ in range(QUANTIDADE):
            rotulo = QLabel()
            rotulo.setTextFormat(Qt.RichText)
            rotulo.setWordWrap(True)
            moldura = QFrame()
            moldura.setStyleSheet("QFrame { border-bottom: 1px solid #1e3a52; }")
            interno = QVBoxLayout(moldura)
            interno.setContentsMargins(0, 2, 0, 4)
            interno.addWidget(rotulo)
            layout.addWidget(moldura)
            self.linhas.append(rotulo)

        self.vazio = QLabel("Faça uma busca na aba Comércio para ver as melhores rotas aqui.")
        self.vazio.setWordWrap(True)
        self.vazio.setProperty("papel", "ajuda")
        layout.addWidget(self.vazio)
        layout.addStretch(1)

        self.rodape = QLabel()
        self.rodape.setProperty("papel", "ajuda")
        layout.addWidget(self.rodape)

        self.c.rotasCalculadas.connect(self.atualizar)
        # Atualiza o "há X min" de vez em quando
        self._relogio = QTimer(self, interval=60_000)
        self._relogio.timeout.connect(self._atualizar_rodape)
        self._relogio.start()
        self.atualizar(self.c.rotas)

    def atualizar(self, rotas: list[Rota]) -> None:
        chave = str(self.c.opcao("ordenacao"))
        self.titulo.setText(f"TOP {QUANTIDADE} · {ORDENACOES.get(chave, ORDENACOES['eficiencia'])[0]}")
        for i, rotulo in enumerate(self.linhas):
            rota = rotas[i] if i < len(rotas) else None
            rotulo.parentWidget().setVisible(rota is not None)
            if rota:
                rotulo.setText(self._html(i + 1, rota))
                rotulo.setToolTip("\n".join(rota.motivos_risco))
        self.vazio.setVisible(not rotas)
        self._atualizar_rodape()

    @staticmethod
    def _html(posicao: int, r: Rota) -> str:
        cor = fmt.CORES_RISCO.get(r.nivel_risco, "#d6e6f2")
        dist = f"{fmt.decimal(r.distancia, 1)} Gm" if r.distancia is not None else "? Gm"
        return (
            f"<b>{posicao}. {r.mercadoria}</b> "
            f"<span style='color:#4cd98a'>+{fmt.compacto(r.lucro)}</span> "
            f"<span style='color:#7f98ad'>({fmt.inteiro(r.scu)} SCU)</span><br>"
            f"<span style='color:#d6e6f2'>{r.origem.rotulo} → {r.destino.rotulo}</span><br>"
            f"<span style='color:#7f98ad'>{dist} · </span>"
            f"<span style='color:{cor}'>risco {r.risco} ({r.nivel_risco})</span>"
        )

    def _atualizar_rodape(self) -> None:
        if self.c.precos_obtidos_em:
            self.rodape.setText(f"Preços UEX {tempo_relativo(self.c.precos_obtidos_em)}")
