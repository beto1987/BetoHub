"""Módulo Contratos: acompanha os contratos do jogo lendo o Game.log do Star Citizen.

Só leitura do arquivo de log (nada é alterado na pasta do jogo). A recompensa e o
prazo não aparecem no log: o jogador informa a recompensa na aba.
"""

from __future__ import annotations

from beto_hub.core.plugin_base import BasePlugin

from .controlador import ControladorContratos
from .logica.repositorio import MIGRACOES


class Plugin(BasePlugin):
    def migracoes(self):
        return MIGRACOES

    def setup(self, ctx):
        super().setup(ctx)
        self.controlador = ControladorContratos(ctx)

    def criar_aba(self, parent):
        from .ui.aba import AbaContratos
        return AbaContratos(self.controlador, parent)

    def criar_painel_overlay(self):
        from .ui.overlay import PainelOverlayContratos
        return PainelOverlayContratos(self.controlador)

    def criar_painel_config(self):
        from .ui.config import PainelConfigContratos
        return PainelConfigContratos(bool(self.controlador.opcao("ler_log")), str(self.controlador.opcao("pasta_jogo")))

    def aplicar_config(self, painel):
        self.ctx.salvar_opcoes({"ler_log": painel.ler_log.isChecked(), "pasta_jogo": painel.pasta.text().strip()})
        self.controlador.reconfigurar()

    def encerrar(self):
        self.controlador.parar()
