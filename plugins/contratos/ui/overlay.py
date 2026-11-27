"""Painel dos Contratos no overlay: contratos ativos com os objetivos, para consultar sem sair do jogo."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from beto_hub.core.i18n import tr
from ..controlador import ControladorContratos
from .comum import COR_SUAVE, duracao
from .detalhe import html_objetivos
from ..logica.rota import Rota, Trecho
from .rota import html_rota


class PainelOverlayContratos(QWidget):
    def __init__(self, c: ControladorContratos, parent=None):
        super().__init__(parent)
        self.c = c
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        self.texto = QLabel()
        self.texto.setTextFormat(Qt.RichText)
        self.texto.setWordWrap(True)
        self.texto.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QScrollArea.NoFrame)
        rolagem.setWidget(self.texto)
        layout.addWidget(rolagem, 1)
        c.contratosAlterados.connect(self.atualizar)
        c.rotaCalculada.connect(self.atualizar)
        self.atualizar()

    def _rota_pendente(self, missoes_ativas: set[str]) -> Rota | None:
        """A última rota sem as paradas de contratos que já terminaram (sem recalcular as distâncias)."""
        rota = self.c.ultima_rota
        if not rota:
            return None
        trechos = [Trecho(t.local, [p for p in t.paradas if p.missao in missoes_ativas], t.distancia)
                   for t in rota.trechos]
        trechos = [t for t in trechos if t.paradas]
        if len(trechos) == len(rota.trechos):
            return rota
        return Rota(trechos, exata=rota.exata, total_valido=False,
                    avisos=[tr("Contratos encerrados saíram da rota; recalcule na aba Contratos.")] if trechos else [])

    def atualizar(self, *_a) -> None:
        ativos = self.c.ativos()
        if not ativos:
            self.texto.setText(f"<span style='color:{COR_SUAVE}'>" + tr("Nenhum contrato ativo. Aceite um no jogo e ele "
                               "aparece aqui em poucos segundos.") + "</span>")
            return
        blocos = []
        rota = self._rota_pendente({c.missao for c in ativos})
        if rota and rota.trechos:
            blocos.append(f"<div style='color:#4cd98a; font-weight:600;'>{tr('ROTA DE ENTREGAS')}</div>"
                          f"<div style='margin-bottom:10px;'>{html_rota(rota, compacto=True)}</div>")
        for c in ativos[:8]:
            feitos, total = c.progresso
            progresso = f" · {feitos}/{total}" if total else ""
            blocos.append(
                f"<div style='margin-bottom:8px;'>"
                f"<div style='color:#35c8f5; font-weight:600;'>{html.escape(c.rotulo)}</div>"
                f"<div style='color:{COR_SUAVE}; font-size:8pt;'>{tr(c.tipo)}{progresso} · {tr('há {tempo}', tempo=duracao(c.duracao_s))}</div>"
                f"{html_objetivos(c, limite=6)}</div>")
        self.texto.setText("".join(blocos))
