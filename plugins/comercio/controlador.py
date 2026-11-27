"""Controlador do Comércio: baixa dados da UEX, calcula rotas e avisa a interface.

Tudo que acessa a rede ou faz conta pesada roda nos workers; a interface só
recebe sinais com os resultados prontos.
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from beto_hub.core.i18n import tr
from beto_hub.core.plugin_base import HubContext
from beto_hub.core.texto import chave_nome

from .logica.modelos import Nave, ParametrosBusca, Preco, Rota, Terminal
from .logica.rotas import aplicar_distancias, calcular_rotas, ordenar

# Opções do módulo em [modulos.comercio] (valores padrão)
PADROES = {
    "nave_id": 0,
    "scu": 46,
    "capital": 100_000,
    "sistema": "Stanton",
    "origem_id": 0,
    "entre_sistemas": False,
    "ignorar_jogadores": True,
    "ordenacao": "eficiencia",
    "distancia_minima": 1.0,      # Gm
    "rotas_com_distancia": 50,    # quantas rotas (as de maior lucro) recebem distância
}


def tempo_relativo(epoch: float) -> str:
    minutos = int((time.time() - epoch) // 60)
    if minutos < 1:
        return tr("agora")
    if minutos < 60:
        return tr("há {n} min", n=minutos)
    horas = minutos // 60
    return tr("há {n} h", n=horas) if horas < 48 else tr("há {n} dias", n=horas // 24)


class ControladorComercio(QObject):
    dadosAtualizados = Signal()          # terminais/preços/naves prontos
    rotasCalculadas = Signal(list)       # list[Rota], já ordenadas
    status = Signal(str, str)            # (texto, papel: "ajuda" | "ok" | "alerta" | "erro")
    ocupado = Signal(bool)
    naveSugerida = Signal(int)           # id UEX da nave ativa escolhida na Frota

    def __init__(self, ctx: HubContext):
        super().__init__()
        self.ctx = ctx
        self.uex = ctx.servico("uex")
        self.terminais: dict[int, Terminal] = {}
        self.precos: list[Preco] = []
        self.naves: list[Nave] = []
        self.rotas: list[Rota] = []
        self.precos_obtidos_em: float | None = None
        self._ultima_busca: ParametrosBusca | None = None
        self._baixando = False
        self._buscando = False
        self._busca_pendente = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self.carregar_dados(forcar=True))
        self._configurar_timer()
        ctx.config.alterado.connect(self._ao_mudar_config)
        self._nave_ativa: dict[str, Any] | None = None
        ctx.eventos.assinar("frota.nave_ativa", self._ao_nave_ativa)

    # ------------------------------------------------------------ opções
    def opcao(self, chave: str) -> Any:
        return self.ctx.opcao(chave, PADROES[chave])

    def _configurar_timer(self) -> None:
        ligado = bool(self.ctx.config.obter("api.atualizacao_automatica", True))
        minutos = max(5, int(self.ctx.config.obter("api.intervalo_minutos", 15)))
        self._timer.setInterval(minutos * 60_000)
        if ligado:
            self._timer.start()
        else:
            self._timer.stop()
        self.ctx.log.debug("Atualização automática: %s (%d min)", "ligada" if ligado else "desligada", minutos)

    def _ao_mudar_config(self, chaves: set[str]) -> None:
        if chaves & {"api.atualizacao_automatica", "api.intervalo_minutos"}:
            self._configurar_timer()
        if chaves & {"api.uex_url", "api.uex_token"}:
            self.carregar_dados(forcar=True)

    # ------------------------------------------------------------ dados
    def carregar_dados(self, forcar: bool = False) -> None:
        if self.uex is None:
            self.status.emit(tr("Serviço da UEX indisponível."), "erro")
            return
        if self._baixando:
            return
        self._baixando = True
        self.ocupado.emit(True)
        self.status.emit(tr("Atualizando preços na UEX…"), "ajuda")
        self.ctx.workers.executar(self._baixar, forcar, ao_concluir=self._ao_baixar, ao_falhar=self._ao_falhar_download)

    def _baixar(self, forcar: bool) -> dict[str, Any]:
        """Roda numa thread de trabalho."""
        terminais = self.uex.terminais()
        precos = self.uex.precos_todos(forcar=forcar)
        try:
            naves = self.uex.naves()
        except Exception as erro:  # a lista de naves é opcional
            self.ctx.log.warning("Lista de naves indisponível: %s", erro)
            naves = None
        return {
            "terminais": {t.id: t for t in map(Terminal.de_uex, terminais.dados or []) if t.id},
            "precos": [p for p in map(Preco.de_uex, precos.dados or []) if p.id_terminal and p.id_mercadoria],
            "naves": sorted(
                (n for n in map(Nave.de_uex, (naves.dados if naves else []) or []) if n.scu > 0),
                key=lambda n: n.nome.lower(),
            ),
            "resultado_precos": precos,
            "aviso": " ".join(a for a in (terminais.aviso, precos.aviso) if a),
        }

    def _ao_baixar(self, r: dict[str, Any]) -> None:
        self._baixando = False
        self.ocupado.emit(False)
        self.terminais, self.precos = r["terminais"], r["precos"]
        if r["naves"]:
            self.naves = r["naves"]
            self._aplicar_nave_ativa()
        self.precos_obtidos_em = r["resultado_precos"].obtido_em
        self._emitir_status_precos(r["aviso"])
        self.dadosAtualizados.emit()
        if self._ultima_busca:  # mantém a tabela e o overlay em dia
            self.buscar(self._ultima_busca)

    def _ao_falhar_download(self, erro: Exception) -> None:
        self._baixando = False
        self.ocupado.emit(False)
        self.status.emit(tr("Não foi possível obter os preços: {erro}", erro=erro), "erro")

    def _emitir_status_precos(self, aviso: str = "", extra: str = "") -> None:
        if self.precos_obtidos_em is None:
            return
        texto = tr("{precos} preços em {terminais} terminais · atualizados {quando}", precos=len(self.precos),
                   terminais=len(self.terminais), quando=tempo_relativo(self.precos_obtidos_em))
        self.status.emit(" ".join(t for t in (aviso, extra, texto) if t), "alerta" if aviso else "ok")

    # ------------------------------------------------------------ nave ativa (módulo Frota)
    def _ao_nave_ativa(self, dados: dict[str, Any]) -> None:
        self._nave_ativa = dados
        self._aplicar_nave_ativa()

    def _aplicar_nave_ativa(self) -> None:
        """Seleciona a nave ativa da Frota, se ela levar carga. Espera a lista de naves chegar."""
        dados = self._nave_ativa
        if not dados or not self.naves:
            return
        self._nave_ativa = None
        if not dados.get("carga_scu"):  # caça, ou nave de mineração (minério não é carga de comércio)
            self.ctx.log.info("Nave ativa %s não leva carga; Comércio mantém a nave atual", dados.get("nome"))
            return
        chaves = set(dados.get("chaves") or [])
        nave = next((n for n in self.naves if chave_nome(n.nome) in chaves), None)
        if nave is None:
            self.ctx.log.info("Nave ativa %s não tem carga na UEX; Comércio mantém a nave atual", dados.get("nome"))
            return
        self.ctx.salvar_opcoes({"nave_id": nave.id, "scu": nave.scu})
        self.naveSugerida.emit(nave.id)

    def sistemas(self) -> list[str]:
        com_preco = {p.id_terminal for p in self.precos}
        return sorted({t.sistema for i, t in self.terminais.items() if i in com_preco and t.sistema})

    def terminais_do_sistema(self, sistema: str) -> list[Terminal]:
        com_compra = {p.id_terminal for p in self.precos if p.compra}
        lista = [t for t in self.terminais.values()
                 if t.id in com_compra and t.disponivel and (not sistema or t.sistema == sistema)]
        return sorted(lista, key=lambda t: t.rotulo.lower())

    # ------------------------------------------------------------ rotas
    def buscar(self, params: ParametrosBusca) -> None:
        if not self.precos:
            self.status.emit(tr("Ainda sem preços. Clique em \"Atualizar preços\"."), "alerta")
            return
        self._ultima_busca = params
        if self._buscando:
            self._busca_pendente = True  # refaz quando a atual terminar
            return
        self._buscando = True
        self.ocupado.emit(True)
        self.status.emit(tr("Calculando rotas e buscando distâncias…"), "ajuda")
        self.ctx.workers.executar(
            self._calcular, params, list(self.precos), dict(self.terminais),
            int(self.opcao("rotas_com_distancia")), float(self.opcao("distancia_minima")),
            ao_concluir=self._ao_calcular, ao_falhar=self._ao_falhar_calculo,
        )

    def _calcular(self, params, precos, terminais, quantas: int, dist_min: float) -> list[Rota]:
        """Roda numa thread de trabalho."""
        candidatas = calcular_rotas(precos, terminais, params)[:max(1, quantas)]
        distancias = self.uex.distancias([(r.origem.id, r.destino.id) for r in candidatas])
        return aplicar_distancias(candidatas, distancias, dist_min)

    def _ao_calcular(self, rotas: list[Rota]) -> None:
        self._buscando = False
        self.ocupado.emit(False)
        if self._busca_pendente:
            self._busca_pendente = False
            self.buscar(self._ultima_busca)
            return
        self.rotas = ordenar(rotas, str(self.opcao("ordenacao")))
        sem_dist = sum(r.distancia is None for r in rotas)
        self.rotasCalculadas.emit(self.rotas)
        if not rotas:
            self.status.emit(tr("Nenhuma rota lucrativa com esses filtros."), "alerta")
        else:
            self._emitir_status_precos(extra=(
                (tr("{n} rotas ({sem} sem distância na UEX)", n=len(rotas), sem=sem_dist) if sem_dist
                 else tr("{n} rotas", n=len(rotas))) + " ·"
            ))

    def _ao_falhar_calculo(self, erro: Exception) -> None:
        self._buscando = False
        self._busca_pendente = False
        self.ocupado.emit(False)
        self.status.emit(tr("Erro ao calcular rotas: {erro}", erro=erro), "erro")

    def reordenar(self, chave: str) -> None:
        self.ctx.salvar_opcoes({"ordenacao": chave})
        self.rotas = ordenar(self.rotas, chave)
        self.rotasCalculadas.emit(self.rotas)

    def parar(self) -> None:
        self._timer.stop()
