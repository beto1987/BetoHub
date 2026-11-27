"""Controlador dos Contratos: acompanha o Game.log do Star Citizen e guarda os contratos.

Ciclo (a cada 2 s, numa thread de trabalho):
  1. lê o que é novo no Game.log da sessão atual e aplica os eventos;
  2. a cada ~1 min, procura logs de sessões anteriores (logbackups) ainda não lidos
     (cobre o que aconteceu com o Hub fechado);
  3. contratos "ativos" parados há dias viram "sem desfecho no log".
Só leitura de arquivos: nada é escrito na pasta do jogo.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from beto_hub.core.i18n import tr
from beto_hub.core.plugin_base import HubContext

from .logica.arquivos import LeitorGameLog, backups, detectar_pasta, ler_linhas
from .logica.eventos import CONCLUIDO, NOMES_STATUS, analisar, local_do_titulo
from .logica.repositorio import Contrato, RepositorioContratos, notas_para_log
from .logica.rota import IndiceLocais, Local, Parada, Rota, melhor_rota, paradas_dos_contratos

INTERVALO_MS = 2000
CICLOS_POR_VARREDURA = 30          # backups a cada ~1 min
AVISAR_SE_MAIS_NOVO_QUE_S = 10 * 60  # não avisa fins antigos lidos ao abrir o Hub

PADROES = {"ler_log": True, "pasta_jogo": "", "local_atual": 0}


class ControladorContratos(QObject):
    contratosAlterados = Signal()
    status = Signal(str, str)  # (texto, papel)
    locaisProntos = Signal()   # terminais da UEX carregados (planejador de rota)
    rotaCalculada = Signal(object)  # Rota | Exception

    def __init__(self, ctx: HubContext):
        super().__init__()
        self.ctx = ctx
        self.log = ctx.log
        self.repo = RepositorioContratos(ctx.banco)
        self.ultimo_status = (tr("Procurando o Game.log do Star Citizen…"), "ajuda")
        self._ocupado = False
        self._ciclos = 0
        self._ultima_leitura: float | None = None

        self._timer = QTimer(self, interval=INTERVALO_MS)
        self._timer.timeout.connect(self._tique)
        self.reconfigurar()

        # Planejador de rota
        self.indice: IndiceLocais | None = None
        self.ultima_rota: Rota | None = None
        self._calculando = False
        self.carregar_locais()

    # ================================================================ configuração
    def opcao(self, chave: str) -> Any:
        return self.ctx.opcao(chave, PADROES[chave])

    @property
    def pasta(self) -> Path | None:
        configurada = str(self.opcao("pasta_jogo") or "").strip()
        return Path(configurada) if configurada else detectar_pasta()

    def reconfigurar(self) -> None:
        """(Re)inicia a leitura conforme as opções. Chamado no início e ao aplicar as Configurações."""
        self._timer.stop()
        if not self.opcao("ler_log"):
            self._emitir_status(tr("Leitura do Game.log desligada (Configurações › Contratos)."), "alerta")
            return
        pasta = self.pasta
        if pasta is None or not pasta.is_dir():
            self._emitir_status(tr("Pasta do Star Citizen não encontrada. Informe-a em Configurações › Contratos."), "erro")
            return
        self.leitor = LeitorGameLog(pasta, self.repo.estado, self.repo.definir_estado)
        self._ciclos = 0
        self._emitir_status(tr("Lendo {pasta}…", pasta=pasta), "ajuda")
        self._executar(self._inicial, pasta)
        self._timer.start()

    # ================================================================ ciclo de leitura
    def _executar(self, funcao, *args) -> None:
        if self._ocupado:
            return
        self._ocupado = True
        self.ctx.workers.executar(funcao, *args, ao_concluir=self._ao_concluir, ao_falhar=self._ao_falhar)

    def _tique(self) -> None:
        self._ciclos += 1
        varrer = self._ciclos % CICLOS_POR_VARREDURA == 0
        self._executar(self._ciclo, self.leitor.pasta, varrer)

    def _inicial(self, pasta: Path) -> dict[str, Any]:
        """Roda numa thread: primeira vez marca os backups existentes como lidos; depois, recupera os novos."""
        if not self.repo.estado("backups_ate"):
            existentes = backups(pasta)
            ultimo = existentes[-1].stat().st_mtime if existentes else 0.0
            self.repo.definir_estado("backups_ate", ultimo)
            self.log.info("Contratos: primeira leitura; %d logs antigos ficam para \"Importar histórico\"",
                          len(existentes))
        r = self._ciclo(pasta, varrer=True)
        return r

    def _ciclo(self, pasta: Path, varrer: bool) -> dict[str, Any]:
        """Roda numa thread de trabalho."""
        mudou = False
        recuperados = 0
        if varrer:
            desde = float(self.repo.estado("backups_ate", "0") or 0)
            for arq in backups(pasta, desde):
                self.repo.aplicar(analisar(ler_linhas(arq)))
                self.repo.definir_estado("backups_ate", arq.stat().st_mtime)
                recuperados += 1
                mudou = True
            if self.repo.encerrar_parados():
                mudou = True

        leitura = self.leitor.ler_novidades()
        encerradas: list[str] = []
        if leitura.linhas:
            eventos = analisar(leitura.linhas)
            if eventos:
                encerradas = self.repo.aplicar(eventos)
                mudou = True
        return {"mudou": mudou, "encerradas": encerradas, "recuperados": recuperados,
                "existe": self.leitor.arquivo.is_file()}

    def _ao_concluir(self, r: dict[str, Any]) -> None:
        self._ocupado = False
        self._ultima_leitura = time.time()
        if r.get("recuperados"):
            self.log.info("Contratos: %d log(s) de sessões anteriores lidos", r["recuperados"])
        if "importados" in r:
            self._emitir_status(tr("Histórico importado: {logs} logs, {contratos} contratos no total.",
                                   logs=r["importados"], contratos=r["contratos"]), "ok")
            self._status_fixo_ate = time.time() + 15  # deixa a mensagem visível por um tempo
        elif time.time() < getattr(self, "_status_fixo_ate", 0):
            pass
        elif not r.get("existe", True):
            self._emitir_status(tr("Esperando o jogo criar {arquivo}.", arquivo=self.leitor.arquivo), "alerta")
        else:
            self._emitir_status(tr("Lendo o Game.log em {pasta} · {n} contrato(s) ativo(s)", pasta=self.leitor.pasta,
                                   n=len(self.repo.ativos())),
                                "ok")
        self._avisar(r.get("encerradas") or [])
        if r.get("mudou"):
            self.contratosAlterados.emit()

    def _ao_falhar(self, erro: Exception) -> None:
        self._ocupado = False
        self._emitir_status(tr("Erro ao ler o Game.log: {erro}", erro=erro), "erro")

    def _avisar(self, missoes: list[str]) -> None:
        agora = time.time()
        for missao in missoes:
            c = self.repo.obter(missao)
            if not c or not c.encerrado_em or agora - c.encerrado_em > AVISAR_SE_MAIS_NOVO_QUE_S:
                continue
            titulo = tr("Contrato concluído") if c.status == CONCLUIDO else tr("Contrato: {status}", status=tr(NOMES_STATUS.get(c.status, c.status)))
            extra = " " + tr("Informe a recompensa na aba Contratos.") if c.status == CONCLUIDO else ""
            self.ctx.notificar(titulo, c.rotulo + extra)

    def _emitir_status(self, texto: str, papel: str) -> None:
        self.ultimo_status = (texto, papel)
        self.status.emit(texto, papel)

    # ================================================================ histórico
    def importar_historico(self) -> bool:
        """Lê todos os logs antigos (pode levar alguns segundos). False se já há uma leitura em andamento."""
        if self._ocupado or not hasattr(self, "leitor"):
            return False
        self._emitir_status(tr("Importando o histórico dos logs antigos…"), "ajuda")
        self._executar(self._importar, self.leitor.pasta)
        return True

    def _importar(self, pasta: Path) -> dict[str, Any]:
        arquivos = backups(pasta)
        for arq in arquivos:
            self.repo.aplicar(analisar(ler_linhas(arq)))
        if arquivos:
            atual = float(self.repo.estado("backups_ate", "0") or 0)
            self.repo.definir_estado("backups_ate", max(atual, arquivos[-1].stat().st_mtime))
        self.repo.encerrar_parados()
        total = len(self.repo.ativos()) + len(self.repo.historico())
        return {"mudou": True, "encerradas": [], "importados": len(arquivos), "contratos": total}

    # ================================================================ dados para a interface
    def ativos(self) -> list[Contrato]:
        return self.repo.ativos()

    def historico(self, desde: float | None = None) -> list[Contrato]:
        return self.repo.historico(desde)

    # ================================================================ ações do jogador
    def salvar_detalhes(self, c: Contrato, recompensa: float | None, notas: str) -> None:
        self.repo.salvar_detalhes(c.missao, recompensa, notas)
        self.contratosAlterados.emit()

    def encerrar_manual(self, c: Contrato, status: str) -> None:
        self.repo.encerrar_manual(c.missao, status)
        self.log.info("Contrato %s marcado como %s pelo jogador", c.rotulo, status)
        self.contratosAlterados.emit()

    def excluir(self, c: Contrato) -> None:
        self.repo.excluir(c.missao)
        self.contratosAlterados.emit()

    def registrar_no_log(self, c: Contrato) -> None:
        """Abre o Log do Capitão pré-preenchido (os módulos conversam por evento)."""
        notas = notas_para_log(c)
        quando = c.encerrado_em or c.aceito_em
        self.ctx.eventos.publicar("log_capitao.registrar_contrato", {
            **({"data": time.strftime("%Y-%m-%d %H:%M", time.localtime(quando))} if quando else {}),
            "titulo": c.rotulo,
            "origem": local_do_titulo(c.titulo),
            "preco_venda": c.recompensa or 0.0,
            "notas": notas,
        })
        self.repo.marcar_registrado(c.missao)
        self.contratosAlterados.emit()

    # ================================================================ planejador de rota
    def carregar_locais(self) -> None:
        """Terminais da UEX (cache de 24 h) para casar os destinos dos contratos."""
        uex = self.ctx.servico("uex")
        if uex is None:
            return
        self.ctx.workers.executar(lambda: IndiceLocais(uex.terminais().dados or []),
                                  ao_concluir=self._ao_locais,
                                  ao_falhar=lambda e: self.log.warning("Locais da UEX indisponíveis: %s", e))

    def _ao_locais(self, indice: IndiceLocais) -> None:
        self.indice = indice
        self.log.info("Contratos: %d locais da UEX para o planejador de rota", len(indice))
        self.locaisProntos.emit()

    def paradas(self) -> list[Parada]:
        return paradas_dos_contratos(self.ativos(), self.indice)

    def calcular_rota(self, paradas: list[Parada], inicio: Local | None) -> bool:
        """Calcula em segundo plano (as distâncias vêm da UEX). False se já há um cálculo em andamento."""
        uex = self.ctx.servico("uex")
        if uex is None or self._calculando:
            return False
        self._calculando = True
        self.ctx.salvar_opcoes({"local_atual": inicio.id_terminal if inicio else 0})
        self.ctx.workers.executar(self._calcular, uex, paradas, inicio,
                                  ao_concluir=self._ao_rota, ao_falhar=self._ao_rota)
        return True

    @staticmethod
    def _calcular(uex, paradas: list[Parada], inicio: Local | None) -> Rota:
        """Roda numa thread: baixa só as distâncias que faltam no cache e resolve a rota."""
        ids = {p.local.id_terminal for p in paradas if p.incluir and p.local}
        if inicio:
            ids.add(inicio.id_terminal)
        pares = [(a, b) for a in ids for b in ids if a < b]
        distancias = uex.distancias(pares) if pares else {}
        return melhor_rota(paradas, lambda a, b: distancias.get((a, b)), inicio)

    def _ao_rota(self, resultado: Rota | Exception) -> None:
        self._calculando = False
        if isinstance(resultado, Rota):
            self.ultima_rota = resultado
        self.rotaCalculada.emit(resultado)

    def parar(self) -> None:
        self._timer.stop()
