"""Módulo Refino: compara métodos por refinaria (estimativas da comunidade UEX),
calcula o lucro previsto, acompanha os pedidos e avisa quando ficam prontos.
"""

from __future__ import annotations

from beto_hub.core.plugin_base import BasePlugin

from .controlador import ControladorRefino
from .logica.pedidos import MIGRACOES


class Plugin(BasePlugin):
    def migracoes(self):
        return MIGRACOES

    def setup(self, ctx):
        super().setup(ctx)
        self.controlador = ControladorRefino(ctx)

    def criar_aba(self, parent):
        from .ui.aba import AbaRefino
        return AbaRefino(self.controlador, parent)

    def criar_painel_overlay(self):
        from .ui.overlay import PainelOverlayRefino
        return PainelOverlayRefino(self.controlador)

    def encerrar(self):
        self.controlador.parar()
