"""Caminhos usados pelo app.

- Configuração (editável pelo usuário): %APPDATA%\\StarHub\\config.toml
- Dados (banco, cache, logs):           %LOCALAPPDATA%\\StarHub\\
  (até a 0.x o app se chamava Beto Hub e usava pastas "BetoHub": elas são copiadas uma vez)
- Código e plugins:                     pasta do app (ou do executável)

Separar dados da pasta do programa evita problemas de permissão quando o app
for instalado em "Arquivos de Programas" pelo instalador.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

NOME_PASTA = "StarHub"
NOME_PASTA_ANTIGA = "BetoHub"  # nome até a versão 0.x
MIGRADAS: list[str] = []  # preenchido pelo main.py (para o log)


def _pasta_env(variavel: str, alternativa: Path) -> Path:
    """Lê uma variável de ambiente do Windows; fora do Windows usa a alternativa."""
    valor = os.environ.get(variavel)
    return Path(valor) if valor else alternativa


def raiz_app() -> Path:
    """Pasta onde estão main.py e plugins/ (ou a pasta interna do PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def raiz_programa() -> Path:
    """Pasta do programa instalado (onde está o StarHub.exe); no código-fonte, a raiz do projeto."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def pasta_plugins() -> Path:
    return raiz_app() / "plugins"


def pasta_tema() -> Path:
    return raiz_app() / "beto_hub" / "ui" / "theme"


def pasta_config() -> Path:
    return _pasta_env("APPDATA", Path.home() / ".config") / NOME_PASTA


def pasta_dados() -> Path:
    return _pasta_env("LOCALAPPDATA", Path.home() / ".local" / "share") / NOME_PASTA


def pasta_logs() -> Path:
    return pasta_dados() / "logs"


def pasta_cache() -> Path:
    return pasta_dados() / "cache"


def arquivo_config() -> Path:
    return pasta_config() / "config.toml"


def arquivo_banco() -> Path:
    return pasta_dados() / "hub.db"


def migrar_pastas_antigas() -> list[str]:
    """Copia as pastas do Beto Hub (0.x) para as do StarHub, se as novas ainda não existirem.

    Copia (não move): a pasta antiga fica como backup. Devolve o que foi copiado.
    """
    copiadas = []
    for nova in (pasta_config(), pasta_dados()):
        antiga = nova.with_name(NOME_PASTA_ANTIGA)
        if antiga.is_dir() and not nova.exists():
            shutil.copytree(antiga, nova, ignore=shutil.ignore_patterns("*.lock"))
            for log_antigo in (nova / "logs").glob("betohub.log*"):
                log_antigo.rename(log_antigo.with_name(log_antigo.name.replace("betohub", "starhub")))
            copiadas.append(f"{antiga} -> {nova}")
    return copiadas


def garantir_pastas() -> None:
    """Cria as pastas de configuração e dados, se ainda não existirem."""
    for pasta in (pasta_config(), pasta_dados(), pasta_logs(), pasta_cache()):
        pasta.mkdir(parents=True, exist_ok=True)
