"""Módulo Mineração: o Star Citizen Beto Scanner dentro do Hub.

Só lê a tela (captura + OCR) e dados da UEX. Não toca no jogo.
"""

from __future__ import annotations

from beto_hub.core.plugin_base import BasePlugin

from .controlador import MIGRACOES, ControladorMineracao


class Plugin(BasePlugin):
    def migracoes(self):
        return MIGRACOES

    def setup(self, ctx):
        super().setup(ctx)
        self.controlador = ControladorMineracao(ctx)

    def criar_aba(self, parent):
        from .ui.aba import AbaMineracao
        return AbaMineracao(self.controlador, parent)

    def criar_painel_overlay(self):
        from .ui.overlay import PainelOverlayMineracao
        return PainelOverlayMineracao(self.controlador)

    def encerrar(self):
        self.controlador.parar()
