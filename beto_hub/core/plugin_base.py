"""Contrato que todo módulo (plugin) do Beto Hub implementa.

Estrutura mínima de um plugin:

    plugins/
      meu_modulo/
        __init__.py
        manifest.toml   -> id, nome, versao, ordem, descricao, api_minima
        plugin.py       -> class Plugin(BasePlugin)

O plugin só acessa o resto do app pelo HubContext (config, banco, eventos,
tarefas, logger, notificações e serviços). Plugins não importam uns aos
outros: conversam pelo barramento de eventos.

Este arquivo não importa o Qt no topo, para a validação de manifesto poder
ser testada sem interface gráfica.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from beto_hub.core.i18n import tr

if TYPE_CHECKING:  # só para o editor/IDE
    from PySide6.QtWidgets import QWidget

    from .config import GerenciadorConfig
    from .database import BancoDados
    from .events import BarramentoEventos
    from .workers import GerenciadorTarefas

# Versão do contrato. Sobe quando BasePlugin/HubContext mudarem de forma
# incompatível; plugins declaram "api_minima" no manifesto.
API_VERSAO = 1

_RE_ID = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


class ErroManifesto(ValueError):
    pass


@dataclass
class Manifesto:
    id: str
    nome: str
    versao: str
    pasta: Path
    descricao: str = ""
    ordem: int = 100
    icone: str = ""
    api_minima: int = 1
    modulo: str = "plugin"   # arquivo .py com a classe
    classe: str = "Plugin"   # nome da classe

    @classmethod
    def de_dict(cls, dados: dict[str, Any], pasta: Path) -> "Manifesto":
        """Valida o conteúdo do manifest.toml. Lança ErroManifesto com mensagem clara."""
        faltando = [c for c in ("id", "nome", "versao") if not dados.get(c)]
        if faltando:
            raise ErroManifesto(tr("manifest.toml sem os campos: {campos}", campos=", ".join(faltando)))

        id_ = str(dados["id"])
        if not _RE_ID.match(id_):
            raise ErroManifesto(
                tr("id inválido '{id}': use só letras minúsculas, números e _ (começando por letra).", id=id_)
            )

        try:
            ordem = int(dados.get("ordem", 100))
            api_minima = int(dados.get("api_minima", 1))
        except (TypeError, ValueError) as erro:
            raise ErroManifesto(tr("'ordem' e 'api_minima' precisam ser números inteiros ({erro}).", erro=erro))

        if api_minima > API_VERSAO:
            raise ErroManifesto(
                tr("Este módulo precisa de uma versão mais nova do Hub (contrato {minimo}, o Hub tem {atual}).",
                   minimo=api_minima, atual=API_VERSAO)
            )

        return cls(
            id=id_,
            nome=str(dados["nome"]),
            versao=str(dados["versao"]),
            pasta=pasta,
            descricao=str(dados.get("descricao", "")),
            ordem=ordem,
            icone=str(dados.get("icone", "")),
            api_minima=api_minima,
            modulo=str(dados.get("modulo", "plugin")),
            classe=str(dados.get("classe", "Plugin")),
        )


@dataclass
class HubContext:
    """Tudo que um plugin pode usar do app."""

    manifesto: Manifesto
    config: "GerenciadorConfig"
    banco: "BancoDados"
    eventos: "BarramentoEventos"
    workers: "GerenciadorTarefas"
    log: logging.Logger
    notificar: Callable[[str, str], None]  # notificar(titulo, mensagem)
    pasta_dados: Path                       # pasta de dados exclusiva do plugin
    servicos: dict[str, Any] = field(default_factory=dict)  # "uex", "ocr"... (próximas etapas)

    # Opções próprias do módulo ficam em [modulos.<id>] no config.toml
    def opcao(self, chave: str, padrao: Any = None) -> Any:
        return self.config.obter(f"modulos.{self.manifesto.id}.{chave}", padrao)

    def salvar_opcoes(self, valores: dict[str, Any]) -> None:
        self.config.atualizar({f"modulos.{self.manifesto.id}.{k}": v for k, v in valores.items()})

    def servico(self, nome: str) -> Any:
        return self.servicos.get(nome)


class BasePlugin:
    """Classe base. Sobrescreva o que o seu módulo precisar."""

    def __init__(self, manifesto: Manifesto):
        self.manifesto = manifesto
        self.ctx: HubContext | None = None

    # 1) Banco: lista de SQL; a posição é a versão. Só acrescente no fim.
    def migracoes(self) -> list[str]:
        return []

    # 2) Inicialização (depois das migrações). Guarde o ctx.
    def setup(self, ctx: HubContext) -> None:
        self.ctx = ctx

    # 3) Conteúdo da aba na janela principal (obrigatório).
    def criar_aba(self, parent: "QWidget") -> "QWidget":
        raise NotImplementedError

    # 4) Painel opcional dentro do overlay (vira uma aba do overlay).
    def criar_painel_overlay(self) -> "QWidget | None":
        return None

    # 5) Seção opcional na tela de Configurações.
    def criar_painel_config(self) -> "QWidget | None":
        return None

    def aplicar_config(self, painel: "QWidget") -> None:
        """Chamado quando o usuário clica OK/Aplicar nas Configurações."""

    # 6) Encerramento: pare timers/threads e salve o que for preciso.
    def encerrar(self) -> None:
        pass
