"""Leitura dos arquivos de log do Star Citizen (só leitura). Sem Qt, testável.

- <pasta do jogo>\\Game.log ............ sessão atual; o jogo recria o arquivo a cada abertura
- <pasta do jogo>\\logbackups\\*.log ... sessões anteriores (o jogo move o Game.log para lá)

`LeitorGameLog` guarda até onde já leu (posição + primeira linha do arquivo, que
muda a cada sessão) para ler só o que é novo a cada ciclo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

NOME_LOG = "Game.log"
PASTA_BACKUPS = "logbackups"
_MAX_LEITURA = 8 * 1024 * 1024  # por ciclo; o resto fica para o próximo


def candidatos_pasta() -> list[Path]:
    """Pastas comuns de instalação (canal LIVE primeiro)."""
    raizes = []
    for unidade in "CDEFG":
        raizes += [Path(f"{unidade}:/Program Files/Roberts Space Industries/StarCitizen"),
                   Path(f"{unidade}:/Roberts Space Industries/StarCitizen"),
                   Path(f"{unidade}:/StarCitizen")]
    return [r / canal for r in raizes for canal in ("LIVE", "PTU", "EPTU", "TECH-PREVIEW")]


def detectar_pasta() -> Path | None:
    """Primeira pasta de jogo com Game.log ou logbackups."""
    for p in candidatos_pasta():
        try:
            if (p / NOME_LOG).is_file() or (p / PASTA_BACKUPS).is_dir():
                return p
        except OSError:
            continue
    return None


def backups(pasta: Path, desde_mtime: float = 0.0) -> list[Path]:
    """Logs de sessões anteriores modificados depois de `desde_mtime`, do mais antigo ao mais novo."""
    try:
        arquivos = [(p.stat().st_mtime, p) for p in (pasta / PASTA_BACKUPS).glob("Game*.log")]
    except OSError:
        return []
    return [p for m, p in sorted(arquivos) if m > desde_mtime]


def ler_linhas(arquivo: Path) -> list[str]:
    with open(arquivo, "rb") as f:
        return f.read().decode("utf-8", errors="replace").splitlines()


@dataclass
class LeituraNova:
    linhas: list[str]
    sessao_nova: bool   # o Game.log foi recriado (jogo reaberto)


class LeitorGameLog:
    """Lê só o que é novo no Game.log. `obter`/`definir` guardam o progresso (no banco)."""

    def __init__(self, pasta: Path, obter: Callable[[str, str], str], definir: Callable[[str, object], None]):
        self.pasta = Path(pasta)
        self._obter, self._definir = obter, definir

    @property
    def arquivo(self) -> Path:
        return self.pasta / NOME_LOG

    def ler_novidades(self) -> LeituraNova:
        try:
            tamanho = os.path.getsize(self.arquivo)
            with open(self.arquivo, "rb") as f:
                assinatura = f.readline(400).decode("utf-8", errors="replace").strip()
                posicao = int(self._obter("posicao", "0") or 0)
                nova = assinatura != self._obter("assinatura", "") or tamanho < posicao
                if nova:
                    posicao = 0
                f.seek(posicao)
                bloco = f.read(_MAX_LEITURA)
        except FileNotFoundError:
            return LeituraNova([], False)

        # Só linhas completas; uma linha pela metade fica para o próximo ciclo
        fim = bloco.rfind(b"\n")
        if fim < 0:
            if nova:
                self._definir("assinatura", assinatura)
                self._definir("posicao", 0)
            return LeituraNova([], nova)
        bloco = bloco[:fim + 1]
        self._definir("assinatura", assinatura)
        self._definir("posicao", posicao + len(bloco))
        return LeituraNova(bloco.decode("utf-8", errors="replace").splitlines(), nova)
