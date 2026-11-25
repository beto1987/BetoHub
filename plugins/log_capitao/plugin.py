"""Módulo Log do Capitão: diário de bordo com as viagens realizadas e anotações.

Outros módulos registram operações publicando eventos com um dicionário:
- "log_capitao.registrar_viagem": mercadoria, origem, destino, scu, preco_compra, preco_venda
- "log_capitao.registrar_refino": mercadoria, origem (refinaria), scu (refinado),
  preco_venda, custo_extra (custo do refino), notas
O Log abre o formulário pré-preenchido para você confirmar os valores reais.
"""

from __future__ import annotations

from beto_hub.core.plugin_base import BasePlugin

from .repositorio import MIGRACOES, TIPO_COMERCIO, TIPO_REFINO, RepositorioLog


class Plugin(BasePlugin):
    def migracoes(self):
        return MIGRACOES

    def setup(self, ctx):
        super().setup(ctx)
        self.repo = RepositorioLog(ctx.banco)
        self.aba = None
        ctx.eventos.assinar("log_capitao.registrar_viagem", lambda d: self._registrar(TIPO_COMERCIO, d))
        ctx.eventos.assinar("log_capitao.registrar_refino", lambda d: self._registrar(TIPO_REFINO, d))

    def criar_aba(self, parent):
        from .ui import AbaLog
        self.aba = AbaLog(self.repo, self.ctx.log, parent)
        return self.aba

    # Sem painel de overlay, como combinado.

    def _registrar(self, tipo: str, dados) -> None:
        if self.aba is None:
            self.ctx.log.warning("Pedido de registro recebido antes da aba existir; ignorado.")
            return
        self.ctx.eventos.publicar("hub.mostrar_aba", self.manifesto.id)
        self.aba.nova(tipo, dict(dados or {}))
