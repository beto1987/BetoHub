"""Arquivo de configuração (TOML com comentários) editável pelo usuário.

- Usa tomlkit para PRESERVAR os comentários ao salvar.
- Chaves novas do padrão são acrescentadas sozinhas em arquivos antigos.
- Arquivo corrompido é guardado como .corrompido-<data> e recriado.
- Toda alteração salva emite o sinal `alterado` com o conjunto de chaves
  mudadas (ex.: {"atalhos.overlay"}) — é isso que permite aplicar o atalho
  na hora, sem reiniciar o app.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

import tomlkit
from PySide6.QtCore import QObject, Signal
from tomlkit.items import Table

from .logging_setup import obter_logger

log = obter_logger("config")

CONFIG_PADRAO = """\
# =====================================================================
#  Star Citizen Beto Hub - arquivo de configuração
#  Pode editar aqui com o app FECHADO, ou usar a tela Configurações.
#  Linhas que começam com # são comentários.
# =====================================================================

[geral]
# Idioma da interface. Por enquanto só "pt-BR".
idioma = "pt-BR"
# Detalhe do log: "DEBUG", "INFO", "WARNING" ou "ERROR".
nivel_log = "INFO"
# true = o X da janela manda o app para a bandeja; false = fecha o app.
fechar_para_bandeja = false

[atalhos]
# Atalho global para mostrar/esconder o overlay.
# Exemplos: "Ctrl+Shift+F10", "Alt+O", "F9". Modificadores: Ctrl, Alt, Shift, Win.
# Funciona com o jogo em foco. As teclas também chegam ao jogo,
# então escolha uma combinação que não faz nada no Star Citizen.
overlay = "Ctrl+Shift+F10"
# true = atalho ligado; false = desligado (padrão).
overlay_ativo = false

# Atalho global para ligar/desligar o "clique atravessa" do overlay.
clique = "Ctrl+Shift+F11"
clique_ativo = false

[overlay]
# Opacidade de 0.20 (bem transparente) a 1.00 (opaco).
opacidade = 0.85
# true = os cliques atravessam o overlay e vão para o jogo.
clique_atravessa = false
# Mostrar o overlay assim que o app abrir.
mostrar_ao_iniciar = false
# Posição e tamanho (atualizados sozinhos ao mover/redimensionar).
x = 40
y = 40
largura = 420
altura = 560
# Última aba aberta no overlay (id do módulo).
aba = ""

[janela]
# -1 = centralizar na tela
x = -1
y = -1
largura = 1200
altura = 760
maximizada = false

[api]
# Token da UEX Corp API 2.0 (crie um app na página "My Apps" do site da UEX).
# Fica salvo em texto puro neste arquivo.
uex_token = ""
uex_url = "https://api.uexcorp.uk/2.0"
atualizacao_automatica = true
# Intervalo da atualização automática dos preços, em minutos.
intervalo_minutos = 15

[plugins]
# Ids dos módulos desativados. Ex.: ["frota", "refino"]
desativados = []

[modulos]
# Cada módulo guarda aqui as próprias opções, em [modulos.<id>].
"""


def _desembrulhar(valor: Any) -> Any:
    """Converte itens do tomlkit em tipos Python comuns (str, int, list, dict)."""
    return valor.unwrap() if hasattr(valor, "unwrap") else valor


def _mesclar_padroes(destino: Table | tomlkit.TOMLDocument, padrao) -> list[str]:
    """Acrescenta ao arquivo do usuário as chaves que só existem no padrão.

    Não sobrescreve nada que o usuário já tenha. Devolve as chaves adicionadas.
    """
    adicionadas: list[str] = []
    for chave, valor in padrao.items():
        if chave not in destino:
            destino[chave] = valor
            adicionadas.append(chave)
        elif isinstance(valor, Table) and isinstance(destino[chave], Table):
            adicionadas += [f"{chave}.{c}" for c in _mesclar_padroes(destino[chave], valor)]
    return adicionadas


class GerenciadorConfig(QObject):
    """Lê, grava e notifica mudanças do config.toml."""

    alterado = Signal(set)  # conjunto de chaves pontuadas que mudaram

    def __init__(self, caminho: Path):
        super().__init__()
        self.caminho = caminho
        self.aviso_carga: str = ""  # mensagem para mostrar ao usuário, se houve problema
        self._doc = self._carregar()

    # ------------------------------------------------------------ leitura
    def _carregar(self) -> tomlkit.TOMLDocument:
        padrao = tomlkit.parse(CONFIG_PADRAO)
        if not self.caminho.exists():
            log.info("Criando configuração padrão em %s", self.caminho)
            self._gravar_texto(CONFIG_PADRAO)
            return padrao

        try:
            doc = tomlkit.parse(self.caminho.read_text(encoding="utf-8"))
        except Exception as erro:  # TOML inválido, encoding errado etc.
            carimbo = time.strftime("%Y%m%d-%H%M%S")
            backup = self.caminho.with_name(f"config.toml.corrompido-{carimbo}")
            shutil.copy2(self.caminho, backup)
            log.error("config.toml inválido (%s). Cópia salva em %s", erro, backup)
            self.aviso_carga = (
                "O arquivo de configuração tinha um erro e foi recriado com os padrões.\n"
                f"A versão antiga foi guardada em:\n{backup}\n\nDetalhe: {erro}"
            )
            self._gravar_texto(CONFIG_PADRAO)
            return padrao

        novas = _mesclar_padroes(doc, padrao)
        if novas:
            log.info("Chaves novas adicionadas à configuração: %s", ", ".join(novas))
            self._gravar_texto(tomlkit.dumps(doc))
        return doc

    def obter(self, chave: str, padrao: Any = None) -> Any:
        """Lê uma chave pontuada, ex.: obter("overlay.opacidade", 0.85)."""
        no: Any = self._doc
        for parte in chave.split("."):
            if not hasattr(no, "get") or parte not in no:
                return padrao
            no = no[parte]
        return _desembrulhar(no)

    # ------------------------------------------------------------ escrita
    def atualizar(self, valores: dict[str, Any], silencioso: bool = False) -> set[str]:
        """Grava várias chaves de uma vez, salva o arquivo e emite `alterado`.

        `silencioso=True` salva sem emitir o sinal (usado para posição de janela).
        Devolve as chaves que realmente mudaram.
        """
        mudadas: set[str] = set()
        for chave, valor in valores.items():
            if self.obter(chave) == valor:
                continue
            *caminho, ultima = chave.split(".")
            no: Any = self._doc
            for parte in caminho:
                if parte not in no:
                    no[parte] = tomlkit.table()
                no = no[parte]
            no[ultima] = valor
            mudadas.add(chave)

        if mudadas:
            self.salvar()
            if not silencioso:
                log.debug("Configuração alterada: %s", ", ".join(sorted(mudadas)))
                self.alterado.emit(mudadas)
        return mudadas

    def definir(self, chave: str, valor: Any) -> None:
        self.atualizar({chave: valor})

    def salvar(self) -> None:
        self._gravar_texto(tomlkit.dumps(self._doc))

    def _gravar_texto(self, texto: str) -> None:
        """Grava de forma atômica: escreve num .tmp e troca (não corrompe se cair a luz)."""
        try:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.caminho.with_suffix(".toml.tmp")
            tmp.write_text(texto, encoding="utf-8")
            os.replace(tmp, self.caminho)
        except OSError:
            log.exception("Não foi possível salvar %s", self.caminho)
            raise
