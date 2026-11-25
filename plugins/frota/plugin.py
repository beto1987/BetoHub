"""Módulo Frota — PROVISÓRIO (esqueleto da etapa 2).

Só mostra uma aba "em construção"; será substituído pelo módulo real.
"""

from beto_hub.core.plugin_base import BasePlugin
from beto_hub.ui.widgets import PainelEmConstrucao


class Plugin(BasePlugin):
    def setup(self, ctx):
        super().setup(ctx)
        ctx.log.debug("Módulo provisório carregado")

    def criar_aba(self, parent):
        return PainelEmConstrucao(
            "Frota",
            "Naves, loadouts e comparação de DPS, escudos e outras estatísticas.",
            "Em uma das próximas etapas",
            parent=parent,
        )
