"""Módulo Frota: hangar do jogador, ficha técnica das naves e comparador.

Fonte das estatísticas: Star Citizen Wiki (dados extraídos do jogo, loadout de fábrica).
A nave ativa é avisada aos outros módulos pelo evento "frota.nave_ativa".
"""

from __future__ import annotations

from beto_hub.core.plugin_base import BasePlugin

from .controlador import ControladorFrota
from .logica.hangar import MIGRACOES


class Plugin(BasePlugin):
    def migracoes(self):
        return MIGRACOES

    def setup(self, ctx):
        super().setup(ctx)
        self.controlador = ControladorFrota(ctx)

    def criar_aba(self, parent):
        from .ui.aba import AbaFrota
        return AbaFrota(self.controlador, parent)
