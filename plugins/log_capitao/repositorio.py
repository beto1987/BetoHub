"""Acesso ao banco do Log do Capitão (sem Qt, testável)."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from beto_hub.core.database import BancoDados

TIPO_COMERCIO = "comercio"
TIPO_REFINO = "refino"
TIPO_CONTRATO = "contrato"
TIPO_ANOTACAO = "anotacao"
NOMES_TIPO = {TIPO_COMERCIO: "Comércio", TIPO_REFINO: "Refino", TIPO_CONTRATO: "Contrato", TIPO_ANOTACAO: "Anotação"}
TIPOS_COM_VALOR = (TIPO_COMERCIO, TIPO_REFINO, TIPO_CONTRATO)  # entradas que têm lucro
# Contrato usa as colunas existentes: titulo (nome do contrato), origem (local),
# preco_venda = recompensa TOTAL (aUEC, não por SCU) e custo_extra = despesas.
FORMATO_DATA = "%Y-%m-%d %H:%M"

MIGRACOES = [
    """
    CREATE TABLE log_capitao_entradas (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        data          TEXT NOT NULL,              -- 'AAAA-MM-DD HH:MM' (hora local)
        tipo          TEXT NOT NULL,              -- 'comercio' | 'anotacao'
        titulo        TEXT NOT NULL DEFAULT '',
        mercadoria    TEXT NOT NULL DEFAULT '',
        origem        TEXT NOT NULL DEFAULT '',
        destino       TEXT NOT NULL DEFAULT '',
        scu           REAL NOT NULL DEFAULT 0,
        preco_compra  REAL NOT NULL DEFAULT 0,    -- aUEC por SCU
        preco_venda   REAL NOT NULL DEFAULT 0,    -- aUEC por SCU
        notas         TEXT NOT NULL DEFAULT '',
        criado_em     TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX ix_log_capitao_data ON log_capitao_entradas(data);
    """,
    # v2 (etapa 5): custo do refino (aUEC) para as entradas do tipo "refino"
    "ALTER TABLE log_capitao_entradas ADD COLUMN custo_extra REAL NOT NULL DEFAULT 0;",
]

# Períodos do filtro: rótulo -> dias (None = tudo; 0 = hoje)
PERIODOS = {"Hoje": 0, "Últimos 7 dias": 7, "Últimos 30 dias": 30, "Tudo": None}


@dataclass
class Entrada:
    data: str = field(default_factory=lambda: datetime.now().strftime(FORMATO_DATA))
    tipo: str = TIPO_COMERCIO
    titulo: str = ""
    mercadoria: str = ""
    origem: str = ""
    destino: str = ""
    scu: float = 0
    preco_compra: float = 0
    preco_venda: float = 0
    notas: str = ""
    custo_extra: float = 0  # refino: custo do refino em aUEC; contrato: despesas
    id: int | None = None

    @property
    def tem_valor(self) -> bool:
        return self.tipo in TIPOS_COM_VALOR

    @property
    def investimento(self) -> float:
        if self.tipo == TIPO_COMERCIO:
            return self.scu * self.preco_compra
        if self.tipo in (TIPO_REFINO, TIPO_CONTRATO):
            return self.custo_extra
        return 0.0

    @property
    def receita(self) -> float:
        if self.tipo == TIPO_CONTRATO:
            return self.preco_venda  # recompensa total
        return self.scu * self.preco_venda if self.tem_valor else 0.0

    @property
    def lucro(self) -> float:
        return self.receita - self.investimento

    @property
    def resumo(self) -> str:
        if self.tipo == TIPO_CONTRATO:
            return self.titulo
        if self.tem_valor:
            return self.mercadoria
        return self.titulo or (self.notas.splitlines()[0][:60] if self.notas else "")

    @classmethod
    def de_linha(cls, linha: Any) -> "Entrada":
        campos = {k: linha[k] for k in linha.keys() if k in cls.__dataclass_fields__}
        return cls(**campos)


def data_inicial(dias: int | None, agora: datetime | None = None) -> str | None:
    if dias is None:
        return None
    agora = agora or datetime.now()
    inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=max(0, dias - 1) if dias else 0)
    return inicio.strftime(FORMATO_DATA)


class RepositorioLog:
    COLUNAS = ("data", "tipo", "titulo", "mercadoria", "origem", "destino",
               "scu", "preco_compra", "preco_venda", "notas", "custo_extra")

    def __init__(self, banco: BancoDados):
        self.banco = banco

    def listar(self, desde: str | None = None) -> list[Entrada]:
        sql = "SELECT * FROM log_capitao_entradas"
        params: tuple = ()
        if desde:
            sql += " WHERE data >= ?"
            params = (desde,)
        sql += " ORDER BY data DESC, id DESC"
        return [Entrada.de_linha(l) for l in self.banco.consultar(sql, params)]

    def salvar(self, e: Entrada) -> int:
        valores = tuple(getattr(e, c) for c in self.COLUNAS)
        if e.id is None:
            marcas = ",".join("?" * len(self.COLUNAS))
            cur = self.banco.executar(
                f"INSERT INTO log_capitao_entradas ({','.join(self.COLUNAS)}) VALUES ({marcas})", valores
            )
            e.id = int(cur.lastrowid)
        else:
            sets = ",".join(f"{c}=?" for c in self.COLUNAS)
            self.banco.executar(f"UPDATE log_capitao_entradas SET {sets} WHERE id=?", (*valores, e.id))
        return e.id

    def excluir(self, id_entrada: int) -> None:
        self.banco.executar("DELETE FROM log_capitao_entradas WHERE id=?", (id_entrada,))

    @staticmethod
    def resumo(entradas: list[Entrada]) -> dict[str, Any]:
        operacoes = [e for e in entradas if e.tem_valor]
        total = sum(e.lucro for e in operacoes)
        return {
            "operacoes": len(operacoes),
            "viagens": sum(e.tipo == TIPO_COMERCIO for e in entradas),
            "refinos": sum(e.tipo == TIPO_REFINO for e in entradas),
            "contratos": sum(e.tipo == TIPO_CONTRATO for e in entradas),
            "lucro_total": total,
            "lucro_medio": total / len(operacoes) if operacoes else 0.0,
            "scu_total": sum(e.scu for e in operacoes),
            "melhor": max(operacoes, key=lambda e: e.lucro, default=None),
        }

    @staticmethod
    def exportar_csv(entradas: list[Entrada], caminho: Path) -> None:
        """CSV com ';' e BOM UTF-8: abre direto no Excel em português."""
        with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Data", "Tipo", "Mercadoria/Título", "Origem", "Destino", "SCU",
                        "Compra (aUEC/SCU)", "Venda (aUEC/SCU)", "Investimento", "Receita", "Lucro", "Notas"])

            def num(v: float) -> str:
                return f"{v:.2f}".replace(".", ",")

            for e in entradas:
                comercio = e.tem_valor
                por_scu = e.tipo in (TIPO_COMERCIO, TIPO_REFINO)
                w.writerow([
                    e.data, NOMES_TIPO.get(e.tipo, e.tipo), e.resumo, e.origem, e.destino,
                    num(e.scu) if por_scu else "", num(e.preco_compra) if por_scu else "",
                    num(e.preco_venda) if por_scu else "", num(e.investimento) if comercio else "",
                    num(e.receita) if comercio else "", num(e.lucro) if comercio else "", e.notas,
                ])
