"""Controlador da Frota: fichas da Star Citizen Wiki, hangar do jogador e nave ativa.

Nave ativa: quando muda, publica o evento "frota.nave_ativa" com
    {"nome", "uuid", "chaves", "carga_scu", "minerio_scu"}
onde "chaves" são os nomes normalizados por beto_hub.core.texto.chave_nome
("MISC Prospector" -> ["miscprospector", "prospector"]). Comércio e Mineração
usam isso para selecionar a mesma nave.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal

from beto_hub.core.plugin_base import HubContext

from .logica.hangar import NaveHangar, RepositorioHangar
from .logica.naves import FichaNave, encontrar, fichas_de_wiki

EVENTO_NAVE_ATIVA = "frota.nave_ativa"


class ControladorFrota(QObject):
    dadosProntos = Signal()
    hangarAlterado = Signal()
    status = Signal(str, str)  # (texto, papel)

    def __init__(self, ctx: HubContext):
        super().__init__()
        self.ctx = ctx
        self.log = ctx.log
        self.repo = RepositorioHangar(ctx.banco)
        self.fichas: list[FichaNave] = []
        self._por_uuid: dict[str, FichaNave] = {}
        self.ultimo_status = ("Carregando dados das naves da Star Citizen Wiki…", "ajuda")
        self._carregando = False
        self.carregar_dados()

    # ================================================================ dados da Wiki
    def carregar_dados(self, forcar: bool = False) -> None:
        wiki = self.ctx.servico("wiki")
        if wiki is None or self._carregando:
            return
        self._carregando = True
        self._emitir_status("Carregando dados das naves da Star Citizen Wiki…", "ajuda")
        self.ctx.workers.executar(self._baixar, wiki, forcar, ao_concluir=self._ao_baixar, ao_falhar=self._ao_falhar)

    @staticmethod
    def _baixar(wiki, forcar: bool) -> tuple[list[FichaNave], Any]:
        """Roda numa thread de trabalho."""
        resultado = wiki.naves(forcar=forcar)
        return fichas_de_wiki(resultado.dados or []), resultado

    def _ao_baixar(self, r: tuple[list[FichaNave], Any]) -> None:
        self._carregando = False
        self.fichas, resultado = r
        self._por_uuid = {f.uuid: f for f in self.fichas}
        versao = next((f.versao for f in self.fichas if f.versao), "")
        self.log.info("Frota: %d naves da Wiki (versão do jogo %s)", len(self.fichas), versao or "?")
        texto = f"{len(self.fichas)} naves · dados do jogo {versao or '?'} (Star Citizen Wiki)"
        if resultado.aviso:
            self._emitir_status(f"{resultado.aviso} {texto}", "alerta")
        else:
            self._emitir_status(texto, "ok")
        self.dadosProntos.emit()

    def _ao_falhar(self, erro: Exception) -> None:
        self._carregando = False
        self._emitir_status(f"Dados das naves indisponíveis: {erro}", "erro")

    def _emitir_status(self, texto: str, papel: str) -> None:
        self.ultimo_status = (texto, papel)
        self.status.emit(texto, papel)

    def ficha(self, nave: NaveHangar | None) -> FichaNave | None:
        if nave is None:
            return None
        return self._por_uuid.get(nave.uuid) or encontrar(self.fichas, nome=nave.nome)

    def ficha_por_uuid(self, uuid: str) -> FichaNave | None:
        return self._por_uuid.get(uuid)

    # ================================================================ hangar
    def hangar(self) -> list[NaveHangar]:
        return self.repo.listar()

    def salvar(self, nave: NaveHangar) -> None:
        self.repo.salvar(nave)
        self.log.info("Hangar: %s salva", nave.rotulo)
        self.hangarAlterado.emit()

    def excluir(self, nave: NaveHangar) -> None:
        self.repo.excluir(nave.id)
        if nave.id == self.id_ativa:
            self.ctx.salvar_opcoes({"nave_ativa": 0})
        self.hangarAlterado.emit()

    # ================================================================ nave ativa
    @property
    def id_ativa(self) -> int:
        return int(self.ctx.opcao("nave_ativa", 0) or 0)

    def definir_ativa(self, nave: NaveHangar) -> None:
        self.ctx.salvar_opcoes({"nave_ativa": nave.id})
        ficha = self.ficha(nave)
        dados = {
            "nome": ficha.nome if ficha else nave.nome,
            "uuid": nave.uuid,
            "chaves": ficha.chaves if ficha else [],
            "carga_scu": ficha.carga_scu if ficha else None,
            "minerio_scu": ficha.minerio_scu if ficha else None,
        }
        self.log.info("Nave ativa: %s", nave.rotulo)
        self.ctx.eventos.publicar(EVENTO_NAVE_ATIVA, dados)
        self.hangarAlterado.emit()
