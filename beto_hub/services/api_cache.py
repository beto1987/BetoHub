"""Cache das respostas de API no SQLite (tabela nucleo_cache_api).

Cada entrada guarda o JSON e quando foi obtido. Quem lê decide a validade
(TTL). Uma entrada vencida continua disponível como "plano B" quando a API
está fora do ar: o app mostra os dados antigos com aviso de idade.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from ..core.database import BancoDados

MIGRACOES_NUCLEO = [
    """
    CREATE TABLE nucleo_cache_api (
        chave      TEXT PRIMARY KEY,
        dados      TEXT NOT NULL,
        obtido_em  REAL NOT NULL
    );
    """,
]


@dataclass
class EntradaCache:
    dados: Any
    obtido_em: float  # epoch (segundos)

    @property
    def idade_s(self) -> float:
        return max(0.0, time.time() - self.obtido_em)

    def valida(self, ttl_s: float) -> bool:
        return self.idade_s < ttl_s


class CacheAPI:
    def __init__(self, banco: BancoDados):
        self.banco = banco

    def ler(self, chave: str) -> EntradaCache | None:
        linha = self.banco.consultar_um(
            "SELECT dados, obtido_em FROM nucleo_cache_api WHERE chave=?", (chave,)
        )
        if not linha:
            return None
        try:
            return EntradaCache(json.loads(linha["dados"]), float(linha["obtido_em"]))
        except (ValueError, TypeError):
            return None  # entrada corrompida: tratamos como inexistente

    def gravar(self, chave: str, dados: Any) -> EntradaCache:
        agora = time.time()
        self.banco.executar(
            "INSERT INTO nucleo_cache_api (chave, dados, obtido_em) VALUES (?, ?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET dados=excluded.dados, obtido_em=excluded.obtido_em",
            (chave, json.dumps(dados, separators=(",", ":")), agora),
        )
        return EntradaCache(dados, agora)

    def ler_varios(self, chaves: list[str]) -> dict[str, EntradaCache]:
        if not chaves:
            return {}
        resultado: dict[str, EntradaCache] = {}
        # SQLite aceita até ~999 parâmetros por consulta: vamos em blocos
        for i in range(0, len(chaves), 500):
            bloco = chaves[i:i + 500]
            marcas = ",".join("?" * len(bloco))
            for linha in self.banco.consultar(
                f"SELECT chave, dados, obtido_em FROM nucleo_cache_api WHERE chave IN ({marcas})", bloco
            ):
                try:
                    resultado[linha["chave"]] = EntradaCache(json.loads(linha["dados"]), float(linha["obtido_em"]))
                except (ValueError, TypeError):
                    pass
        return resultado

    def limpar(self, prefixo: str = "") -> int:
        cur = self.banco.executar("DELETE FROM nucleo_cache_api WHERE chave LIKE ?", (prefixo + "%",))
        return cur.rowcount
