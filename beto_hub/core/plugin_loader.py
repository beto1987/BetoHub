"""Descobre, valida e carrega os plugins da pasta plugins/.

Um plugin com problema NÃO derruba o app: ele vira um registro com
estado "erro" e a janela mostra uma aba explicando o que aconteceu.
"""

from __future__ import annotations

import importlib
import sys
import tomllib
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from beto_hub.core.i18n import tr
from .logging_setup import obter_logger
from .plugin_base import BasePlugin, ErroManifesto, HubContext, Manifesto

log = obter_logger("plugins")

OK, ERRO, DESATIVADO = "ok", "erro", "desativado"


@dataclass
class PluginCarregado:
    pasta: Path
    manifesto: Manifesto | None
    estado: str
    instancia: BasePlugin | None = None
    erro: str = ""
    detalhe: str = ""  # traceback completo, para a aba de erro

    @property
    def id(self) -> str:
        return self.manifesto.id if self.manifesto else self.pasta.name

    @property
    def nome(self) -> str:
        return self.manifesto.nome if self.manifesto else self.pasta.name


def ler_manifesto(pasta: Path) -> Manifesto:
    arquivo = pasta / "manifest.toml"
    try:
        with arquivo.open("rb") as f:
            dados = tomllib.load(f)
    except tomllib.TOMLDecodeError as erro:
        raise ErroManifesto(tr("manifest.toml inválido: {erro}", erro=erro)) from erro
    return Manifesto.de_dict(dados, pasta)


class CarregadorPlugins:
    def __init__(self, pasta_plugins: Path, desativados: list[str] | None = None):
        self.pasta = pasta_plugins
        self.desativados = set(desativados or [])

    def descobrir(self) -> list[Path]:
        """Pastas que parecem plugins (têm manifest.toml)."""
        if not self.pasta.is_dir():
            log.warning("Pasta de plugins não encontrada: %s", self.pasta)
            return []
        return sorted(p for p in self.pasta.iterdir() if p.is_dir() and (p / "manifest.toml").is_file())

    def carregar_todos(
        self,
        criar_contexto: Callable[[Manifesto], HubContext],
        migrar: Callable[[str, list[str]], int] | None = None,
    ) -> list[PluginCarregado]:
        # O pacote "plugins" precisa estar importável (pasta pai no sys.path)
        raiz = str(self.pasta.parent)
        if raiz not in sys.path:
            sys.path.insert(0, raiz)

        resultado: list[PluginCarregado] = []
        ids_vistos: set[str] = set()

        for pasta in self.descobrir():
            # 1) Manifesto
            try:
                manifesto = ler_manifesto(pasta)
            except ErroManifesto as erro:
                log.error("Plugin em %s ignorado: %s", pasta.name, erro)
                resultado.append(PluginCarregado(pasta, None, ERRO, erro=str(erro)))
                continue

            if manifesto.id in ids_vistos:
                msg = tr("Id '{id}' repetido em outro plugin.", id=manifesto.id)
                log.error(msg)
                resultado.append(PluginCarregado(pasta, manifesto, ERRO, erro=msg))
                continue
            ids_vistos.add(manifesto.id)

            if manifesto.id in self.desativados:
                log.info("Plugin %s desativado pela configuração", manifesto.id)
                resultado.append(PluginCarregado(pasta, manifesto, DESATIVADO))
                continue

            # 2) Importação, migrações e setup
            resultado.append(self._carregar(pasta, manifesto, criar_contexto, migrar))

        resultado.sort(key=lambda p: (p.manifesto.ordem if p.manifesto else 999, p.nome.lower()))
        return resultado

    def _carregar(self, pasta, manifesto, criar_contexto, migrar) -> PluginCarregado:
        nome_modulo = f"{self.pasta.name}.{pasta.name}.{manifesto.modulo}"
        try:
            modulo = importlib.import_module(nome_modulo)
            classe = getattr(modulo, manifesto.classe, None)
            if classe is None or not (isinstance(classe, type) and issubclass(classe, BasePlugin)):
                raise TypeError(
                    tr("{modulo} não tem a classe '{classe}' derivada de BasePlugin.", modulo=nome_modulo,
                       classe=manifesto.classe)
                )
            instancia: BasePlugin = classe(manifesto)
            if migrar:
                migrar(manifesto.id, instancia.migracoes())
            instancia.setup(criar_contexto(manifesto))
        except Exception as erro:
            log.exception("Falha ao carregar o plugin %s", manifesto.id)
            return PluginCarregado(
                pasta, manifesto, ERRO,
                erro=f"{type(erro).__name__}: {erro}",
                detalhe=traceback.format_exc(),
            )
        log.info("Plugin carregado: %s v%s", manifesto.id, manifesto.versao)
        return PluginCarregado(pasta, manifesto, OK, instancia=instancia)
