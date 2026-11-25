"""Módulo Comércio: rotas de compra e venda mais eficientes, com nota de risco.

Fonte dos dados: UEX Corp API 2.0 (preços reportados pela comunidade).
"""

from __future__ import annotations

from beto_hub.core.plugin_base import BasePlugin

from .controlador import PADROES, ControladorComercio


class Plugin(BasePlugin):
    def setup(self, ctx):
        super().setup(ctx)
        self.controlador = ControladorComercio(ctx)
        self.controlador.carregar_dados(forcar=False)  # usa o cache se ainda for recente

    def criar_aba(self, parent):
        from .ui.aba import AbaComercio
        return AbaComercio(self.controlador, self._enviar_ao_log, parent)

    def criar_painel_overlay(self):
        from .ui.overlay import PainelOverlayComercio
        return PainelOverlayComercio(self.controlador)

    def criar_painel_config(self):
        from .ui.config import PainelConfigComercio
        return PainelConfigComercio(
            float(self.ctx.opcao("distancia_minima", PADROES["distancia_minima"])),
            int(self.ctx.opcao("rotas_com_distancia", PADROES["rotas_com_distancia"])),
        )

    def aplicar_config(self, painel):
        self.ctx.salvar_opcoes({
            "distancia_minima": round(painel.distancia_minima.value(), 1),
            "rotas_com_distancia": painel.rotas_com_distancia.value(),
        })

    def _enviar_ao_log(self, rota) -> None:
        # O Log do Capitão escuta este evento (módulos não se importam diretamente)
        self.ctx.eventos.publicar("log_capitao.registrar_viagem", rota.para_log())

    def encerrar(self):
        self.controlador.parar()
