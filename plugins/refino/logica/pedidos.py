"""Pedidos de refino salvos no banco (tabela refino_pedidos). Sem Qt, testável."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from beto_hub.core import i18n
from beto_hub.core.i18n import N_
from beto_hub.core.database import BancoDados

ANDAMENTO, PRONTO, RETIRADO = "andamento", "pronto", "retirado"
NOMES_STATUS = {ANDAMENTO: N_("Refinando"), PRONTO: N_("Pronto"), RETIRADO: N_("Retirado")}

MIGRACOES = [
    """
    CREATE TABLE refino_pedidos (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        refinaria       TEXT NOT NULL,
        id_terminal     INTEGER NOT NULL DEFAULT 0,
        metodo          TEXT NOT NULL DEFAULT '',
        inicio          REAL NOT NULL,              -- epoch (segundos)
        minutos         REAL NOT NULL DEFAULT 0,    -- duração informada pelo jogo
        custo           REAL NOT NULL DEFAULT 0,    -- aUEC
        itens           TEXT NOT NULL DEFAULT '[]', -- JSON: [{nome, chave, quantidade_cscu, refinado_scu}]
        valor_estimado  REAL,                       -- aUEC (pode ser nulo)
        status          TEXT NOT NULL DEFAULT 'andamento',
        notas           TEXT NOT NULL DEFAULT '',
        criado_em       TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX ix_refino_pedidos_status ON refino_pedidos(status);
    """,
]


@dataclass
class Pedido:
    refinaria: str
    metodo: str
    minutos: float
    custo: float
    itens: list[dict[str, Any]] = field(default_factory=list)
    inicio: float = field(default_factory=time.time)
    id_terminal: int = 0
    valor_estimado: float | None = None
    status: str = ANDAMENTO
    notas: str = ""
    id: int | None = None

    @property
    def fim(self) -> float:
        return self.inicio + self.minutos * 60

    def restante_s(self, agora: float | None = None) -> float:
        return max(0.0, self.fim - (agora or time.time()))

    @property
    def descricao_itens(self) -> str:
        return ", ".join(f"{i.get('nome', '?')} ({i18n.numero(i.get('quantidade_cscu', 0))} cSCU)"
                         for i in self.itens)

    @property
    def refinado_scu(self) -> float | None:
        valores = [i.get("refinado_scu") for i in self.itens]
        return None if not valores or any(v is None for v in valores) else sum(valores)

    @property
    def lucro_estimado(self) -> float | None:
        return None if self.valor_estimado is None else self.valor_estimado - self.custo

    @classmethod
    def de_linha(cls, l: Any) -> "Pedido":
        return cls(
            id=l["id"], refinaria=l["refinaria"], id_terminal=l["id_terminal"], metodo=l["metodo"],
            inicio=l["inicio"], minutos=l["minutos"], custo=l["custo"], itens=json.loads(l["itens"] or "[]"),
            valor_estimado=l["valor_estimado"], status=l["status"], notas=l["notas"],
        )


class RepositorioPedidos:
    COLUNAS = ("refinaria", "id_terminal", "metodo", "inicio", "minutos", "custo",
               "itens", "valor_estimado", "status", "notas")

    def __init__(self, banco: BancoDados):
        self.banco = banco

    def _valores(self, p: Pedido) -> tuple:
        return (p.refinaria, p.id_terminal, p.metodo, p.inicio, p.minutos, p.custo,
                json.dumps(p.itens, ensure_ascii=False), p.valor_estimado, p.status, p.notas)

    def salvar(self, p: Pedido) -> int:
        if p.id is None:
            marcas = ",".join("?" * len(self.COLUNAS))
            cur = self.banco.executar(
                f"INSERT INTO refino_pedidos ({','.join(self.COLUNAS)}) VALUES ({marcas})", self._valores(p))
            p.id = int(cur.lastrowid)
        else:
            sets = ",".join(f"{c}=?" for c in self.COLUNAS)
            self.banco.executar(f"UPDATE refino_pedidos SET {sets} WHERE id=?", (*self._valores(p), p.id))
        return p.id

    def listar(self, incluir_retirados: bool = False, limite: int = 200) -> list[Pedido]:
        filtro = "" if incluir_retirados else f"WHERE status != '{RETIRADO}'"
        linhas = self.banco.consultar(
            f"SELECT * FROM refino_pedidos {filtro} "
            f"ORDER BY CASE status WHEN '{PRONTO}' THEN 0 WHEN '{ANDAMENTO}' THEN 1 ELSE 2 END, "
            "inicio + minutos * 60 ASC LIMIT ?", (limite,))
        return [Pedido.de_linha(l) for l in linhas]

    def definir_status(self, id_pedido: int, status: str) -> None:
        self.banco.executar("UPDATE refino_pedidos SET status=? WHERE id=?", (status, id_pedido))

    def excluir(self, id_pedido: int) -> None:
        self.banco.executar("DELETE FROM refino_pedidos WHERE id=?", (id_pedido,))

    def marcar_prontos(self, agora: float | None = None) -> list[Pedido]:
        """Passa para "pronto" os pedidos cujo tempo acabou. Devolve os que mudaram agora."""
        agora = agora or time.time()
        linhas = self.banco.consultar(
            f"SELECT * FROM refino_pedidos WHERE status='{ANDAMENTO}' AND inicio + minutos * 60 <= ?", (agora,))
        prontos = [Pedido.de_linha(l) for l in linhas]
        for p in prontos:
            self.definir_status(p.id, PRONTO)
            p.status = PRONTO
        return prontos
