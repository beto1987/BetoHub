"""Configuração de logs: arquivo rotativo + console.

Todos os loggers do app ficam sob "betohub" (ex.: "betohub.plugin.comercio"),
então mudar o nível em tempo real afeta o app inteiro.
"""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

NOME_RAIZ = "betohub"
NIVEIS_VALIDOS = ("DEBUG", "INFO", "WARNING", "ERROR")
_FORMATO = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"


def configurar_logs(pasta_logs: Path, nivel: str = "INFO") -> logging.Logger:
    """Cria os handlers (uma vez só) e devolve o logger raiz do app."""
    logger = logging.getLogger(NOME_RAIZ)
    if logger.handlers:  # já configurado
        definir_nivel(nivel)
        return logger

    pasta_logs.mkdir(parents=True, exist_ok=True)
    formato = logging.Formatter(_FORMATO, datefmt="%Y-%m-%d %H:%M:%S")

    # 2 MB por arquivo, guarda os 5 últimos (starhub.log.1 ... .5)
    arquivo = RotatingFileHandler(
        pasta_logs / "starhub.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    arquivo.setFormatter(formato)
    logger.addHandler(arquivo)

    # Console só existe quando rodando com python.exe (debug.bat)
    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formato)
        logger.addHandler(console)

    logger.propagate = False
    definir_nivel(nivel)
    _instalar_captura_excecoes(logger)
    return logger


def definir_nivel(nivel: str) -> None:
    """Muda o nível de log em tempo real (usado pela tela de configurações)."""
    nivel = (nivel or "INFO").upper()
    if nivel not in NIVEIS_VALIDOS:
        nivel = "INFO"
    logging.getLogger(NOME_RAIZ).setLevel(getattr(logging, nivel))


def obter_logger(nome: str) -> logging.Logger:
    """Atalho para criar loggers filhos: obter_logger("ui") -> betohub.ui"""
    return logging.getLogger(f"{NOME_RAIZ}.{nome}")


def _instalar_captura_excecoes(logger: logging.Logger) -> None:
    """Garante que erros não tratados (na thread principal ou em threads) vão para o log."""

    def excecao_principal(tipo, valor, tb):
        if issubclass(tipo, KeyboardInterrupt):
            sys.__excepthook__(tipo, valor, tb)
            return
        logger.critical("Erro não tratado", exc_info=(tipo, valor, tb))

    def excecao_thread(args: threading.ExceptHookArgs):
        logger.critical(
            "Erro não tratado na thread %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = excecao_principal
    threading.excepthook = excecao_thread
