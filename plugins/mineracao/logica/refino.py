"""Melhores refinarias para um minério, com dados da UEX (refineries_yields).

A UEX informa, por refinaria e mercadoria, o bônus de rendimento em %.
Os nomes podem vir como "Quantainium (Raw)" ou "Quantainium (Ore)"; a
comparação ignora esses sufixos, maiúsculas e acentos.

Se a UEX nunca respondeu (sem cache), usa o arquivo antigo do Beto Scanner
(refineries_reserva.json) e avisa que os dados podem estar desatualizados.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Refinaria:
    nome: str
    sistema: str
    bonus: float  # %

    @property
    def rotulo(self) -> str:
        sistema = f" ({self.sistema})" if self.sistema and f"({self.sistema})" not in self.nome else ""
        sinal = "+" if self.bonus >= 0 else ""
        return f"{self.nome}{sistema} {sinal}{self.bonus:g}%"


def chave_minerio(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    sem_sufixo = re.sub(r"\((raw|ore|bruto|minerio)\)|\b(raw|ore)\b", "", sem_acento, flags=re.I)
    return re.sub(r"[^a-z]", "", sem_sufixo.lower())


class TabelaRefino:
    def __init__(self, por_minerio: dict[str, list[Refinaria]], fonte: str):
        self._por = por_minerio
        self.fonte = fonte  # "uex" ou "arquivo"

    @classmethod
    def de_uex(cls, linhas: list[dict[str, Any]]) -> "TabelaRefino":
        por: dict[str, dict[str, Refinaria]] = {}
        for l in linhas or []:
            try:
                bonus = float(l.get("value"))
            except (TypeError, ValueError):
                continue
            nome = l.get("terminal_name") or l.get("space_station_name") or l.get("city_name") or "?"
            chave = chave_minerio(l.get("commodity_name", ""))
            if not chave:
                continue
            atual = por.setdefault(chave, {})
            if nome not in atual or bonus > atual[nome].bonus:
                atual[nome] = Refinaria(nome, l.get("star_system_name") or "", bonus)
        return cls({k: sorted(v.values(), key=lambda r: -r.bonus) for k, v in por.items()}, "uex")

    @classmethod
    def de_arquivo(cls, arquivo: Path) -> "TabelaRefino":
        try:
            with open(arquivo, "r", encoding="utf-8") as f:
                ores = json.load(f).get("ores", {})
        except (OSError, ValueError):
            ores = {}
        por = {
            chave_minerio(nome): sorted(
                (Refinaria(r["station"], r.get("system", ""), float(r["bonus"])) for r in linhas),
                key=lambda r: -r.bonus)
            for nome, linhas in ores.items()
        }
        return cls(por, "arquivo")

    def melhores(self, minerio: str, quantas: int = 3) -> list[Refinaria] | None:
        """Refinarias com bônus positivo, da melhor para a pior. None = sem dados do minério."""
        linhas = self._por.get(chave_minerio(minerio))
        if linhas is None:
            return None
        return [r for r in linhas if r.bonus > 0][:quantas]

    def __len__(self) -> int:
        return len(self._por)
