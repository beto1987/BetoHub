"""Contratos e objetivos no banco (tabelas contratos_*). Sem Qt, testável.

`aplicar` é idempotente: ler o mesmo log duas vezes (ao vivo e depois pelo backup)
não duplica nem "desfaz" nada. Chave do contrato = MissionId do jogo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from beto_hub.core.database import BancoDados

from .eventos import (
    ABANDONADO, ACEITO, ATIVO, CONCLUIDO, DEFINICAO, FALHOU, ENCERRADO, FIM_NOTIFICADO, OBJ_CONCLUIDO, OBJ_RETIRADO, OBJETIVO, SEM_FIM,
    Evento, classificar, nome_legivel,
)

OBJ_ATIVO, OBJ_FEITO, OBJ_CANCELADO = "ativo", "concluido", "retirado"
PARADO_APOS_S = 3 * 24 * 3600  # ativo sem novidade há 3 dias -> "sem desfecho no log"

MIGRACOES = [
    """
    CREATE TABLE contratos_contratos (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        missao         TEXT NOT NULL UNIQUE,         -- MissionId do jogo
        titulo         TEXT NOT NULL DEFAULT '',
        nome_interno   TEXT NOT NULL DEFAULT '',     -- ex.: HaulCargo_MultiToSingle_... (plano B do título)
        tipo           TEXT NOT NULL DEFAULT '',
        reputacao      TEXT NOT NULL DEFAULT '',
        aceito_em      REAL,                         -- epoch
        encerrado_em   REAL,
        status         TEXT NOT NULL DEFAULT 'ativo',
        recompensa     REAL,                         -- aUEC, informada pelo jogador
        notas          TEXT NOT NULL DEFAULT '',
        registrado_log INTEGER NOT NULL DEFAULT 0    -- já enviado ao Log do Capitão
    );
    CREATE INDEX ix_contratos_status ON contratos_contratos(status);
    CREATE TABLE contratos_objetivos (
        missao         TEXT NOT NULL,
        objetivo       TEXT NOT NULL,
        texto          TEXT NOT NULL DEFAULT '',
        status         TEXT NOT NULL DEFAULT 'ativo',
        ordem          REAL NOT NULL DEFAULT 0,      -- epoch de quando apareceu
        PRIMARY KEY (missao, objetivo)
    );
    CREATE TABLE contratos_estado (
        chave          TEXT PRIMARY KEY,
        valor          TEXT NOT NULL
    );
    """,
]


@dataclass
class Objetivo:
    id: str
    texto: str
    status: str = OBJ_ATIVO


@dataclass
class Contrato:
    missao: str
    titulo: str = ""
    nome_interno: str = ""
    tipo: str = ""
    reputacao: str = ""
    aceito_em: float | None = None
    encerrado_em: float | None = None
    status: str = ATIVO
    recompensa: float | None = None
    notas: str = ""
    registrado_log: bool = False
    id: int | None = None
    objetivos: list[Objetivo] = field(default_factory=list)

    @property
    def ativo(self) -> bool:
        return self.status == ATIVO

    @property
    def rotulo(self) -> str:
        return self.titulo or nome_legivel(self.nome_interno) or "(contrato sem título no log)"

    @property
    def duracao_s(self) -> float | None:
        if self.aceito_em is None:
            return None
        fim = self.encerrado_em if self.encerrado_em is not None else time.time()
        return max(0.0, fim - self.aceito_em)

    @property
    def progresso(self) -> tuple[int, int]:
        """(concluídos, total) sem contar os retirados."""
        validos = [o for o in self.objetivos if o.status != OBJ_CANCELADO]
        return sum(o.status == OBJ_FEITO for o in validos), len(validos)


class RepositorioContratos:
    def __init__(self, banco: BancoDados):
        self.banco = banco

    # ------------------------------------------------------------ eventos do log
    def aplicar(self, eventos: Iterable[Evento]) -> list[str]:
        """Grava os eventos. Devolve as missões que ENCERRARAM agora (para avisar o jogador)."""
        encerradas: list[str] = []
        tocadas: set[str] = set()
        with self.banco.transacao() as con:
            for e in eventos:
                tocadas.add(e.missao)
                if e.tipo == ACEITO:
                    self._garantir(con, e.missao, e.quando)
                    con.execute("UPDATE contratos_contratos SET titulo=?, reputacao=? WHERE missao=?",
                                (e.titulo, e.reputacao, e.missao))
                    con.execute("UPDATE contratos_contratos SET aceito_em=? WHERE missao=? AND "
                                "(aceito_em IS NULL OR aceito_em > ?)", (e.quando, e.missao, e.quando))
                elif e.tipo == OBJETIVO:
                    self._garantir(con, e.missao, e.quando)
                    con.execute(
                        "INSERT INTO contratos_objetivos (missao, objetivo, texto, ordem) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(missao, objetivo) DO UPDATE SET texto=excluded.texto "
                        "WHERE excluded.ordem >= contratos_objetivos.ordem",
                        (e.missao, e.objetivo, e.texto, e.quando))
                elif e.tipo in (OBJ_CONCLUIDO, OBJ_RETIRADO):
                    novo = OBJ_FEITO if e.tipo == OBJ_CONCLUIDO else OBJ_CANCELADO
                    con.execute("UPDATE contratos_objetivos SET status=? WHERE missao=? AND objetivo=?",
                                (novo, e.missao, e.objetivo))
                elif e.tipo == DEFINICAO:
                    self._garantir(con, e.missao, e.quando)
                    con.execute("UPDATE contratos_contratos SET nome_interno=? WHERE missao=? AND nome_interno=''",
                                (e.texto, e.missao))
                elif e.tipo in (ENCERRADO, FIM_NOTIFICADO):
                    self._garantir(con, e.missao, None)
                    if e.titulo:
                        con.execute("UPDATE contratos_contratos SET titulo=?, reputacao=? WHERE missao=? AND titulo=''",
                                    (e.titulo, e.reputacao, e.missao))
                    cur = con.execute(
                        "UPDATE contratos_contratos SET status=?, encerrado_em=? WHERE missao=? AND status IN (?, ?)",
                        (e.resultado, e.quando, e.missao, ATIVO, SEM_FIM))
                    if cur.rowcount:
                        encerradas.append(e.missao)
                        if e.resultado == CONCLUIDO:  # nem todo objetivo concluído aparece no log
                            con.execute("UPDATE contratos_objetivos SET status=? WHERE missao=? AND status=?",
                                        (OBJ_FEITO, e.missao, OBJ_ATIVO))
            self._classificar(con, tocadas)
        return encerradas

    def encerrar_parados(self, agora: float | None = None, limite_s: float = PARADO_APOS_S) -> int:
        """Contratos "ativos" sem novidade há muito tempo: o log nunca mostrou o fim (jogo fechou, travou…).

        Passam para "sem desfecho no log". Se o fim aparecer depois, `aplicar` ainda atualiza.
        """
        corte = (agora or time.time()) - limite_s
        cur = self.banco.executar(
            "UPDATE contratos_contratos SET status=?, encerrado_em=COALESCE("
            "  (SELECT MAX(ordem) FROM contratos_objetivos o WHERE o.missao=contratos_contratos.missao), aceito_em) "
            "WHERE status=? AND COALESCE("
            "  (SELECT MAX(ordem) FROM contratos_objetivos o WHERE o.missao=contratos_contratos.missao), aceito_em, 0) < ?",
            (SEM_FIM, ATIVO, corte))
        return cur.rowcount

    @staticmethod
    def _garantir(con, missao: str, quando: float | None) -> None:
        con.execute("INSERT OR IGNORE INTO contratos_contratos (missao, aceito_em) VALUES (?, ?)", (missao, quando))

    @staticmethod
    def _classificar(con, missoes: set[str]) -> None:
        for missao in missoes:
            linha = con.execute("SELECT titulo, nome_interno FROM contratos_contratos WHERE missao=?",
                                (missao,)).fetchone()
            if not linha:
                continue
            textos = [r[0] for r in con.execute("SELECT texto FROM contratos_objetivos WHERE missao=?", (missao,))]
            textos.append(nome_legivel(linha[1]))
            con.execute("UPDATE contratos_contratos SET tipo=? WHERE missao=?", (classificar(linha[0], textos), missao))

    # ------------------------------------------------------------ consultas
    def _montar(self, linhas: list[Any]) -> list[Contrato]:
        contratos = [Contrato(
            id=l["id"], missao=l["missao"], titulo=l["titulo"], nome_interno=l["nome_interno"], tipo=l["tipo"],
            reputacao=l["reputacao"],
            aceito_em=l["aceito_em"], encerrado_em=l["encerrado_em"], status=l["status"],
            recompensa=l["recompensa"], notas=l["notas"], registrado_log=bool(l["registrado_log"]),
        ) for l in linhas]
        if contratos:
            por_missao = {c.missao: c for c in contratos}
            marcas = ",".join("?" * len(por_missao))
            for o in self.banco.consultar(
                    f"SELECT * FROM contratos_objetivos WHERE missao IN ({marcas}) ORDER BY ordem, objetivo",
                    list(por_missao)):
                por_missao[o["missao"]].objetivos.append(Objetivo(o["objetivo"], o["texto"], o["status"]))
        return contratos

    def ativos(self) -> list[Contrato]:
        return self._montar(self.banco.consultar(
            "SELECT * FROM contratos_contratos WHERE status=? ORDER BY aceito_em DESC", (ATIVO,)))

    def historico(self, desde: float | None = None, limite: int = 2000) -> list[Contrato]:
        sql, params = "SELECT * FROM contratos_contratos WHERE status != ?", [ATIVO]
        if desde is not None:
            sql += " AND COALESCE(encerrado_em, aceito_em, 0) >= ?"
            params.append(desde)
        sql += " ORDER BY COALESCE(encerrado_em, aceito_em) DESC LIMIT ?"
        params.append(limite)
        return self._montar(self.banco.consultar(sql, params))

    def obter(self, missao: str) -> Contrato | None:
        r = self._montar(self.banco.consultar("SELECT * FROM contratos_contratos WHERE missao=?", (missao,)))
        return r[0] if r else None

    # ------------------------------------------------------------ edição pelo jogador
    def salvar_detalhes(self, missao: str, recompensa: float | None, notas: str) -> None:
        self.banco.executar("UPDATE contratos_contratos SET recompensa=?, notas=? WHERE missao=?",
                            (recompensa, notas.strip(), missao))

    def encerrar_manual(self, missao: str, status: str, quando: float | None = None) -> None:
        self.banco.executar("UPDATE contratos_contratos SET status=?, encerrado_em=? WHERE missao=?",
                            (status, quando or time.time(), missao))

    def marcar_registrado(self, missao: str) -> None:
        self.banco.executar("UPDATE contratos_contratos SET registrado_log=1 WHERE missao=?", (missao,))

    def excluir(self, missao: str) -> None:
        with self.banco.transacao() as con:
            con.execute("DELETE FROM contratos_objetivos WHERE missao=?", (missao,))
            con.execute("DELETE FROM contratos_contratos WHERE missao=?", (missao,))

    # ------------------------------------------------------------ estado da leitura
    def estado(self, chave: str, padrao: str = "") -> str:
        l = self.banco.consultar_um("SELECT valor FROM contratos_estado WHERE chave=?", (chave,))
        return l["valor"] if l else padrao

    def definir_estado(self, chave: str, valor: Any) -> None:
        self.banco.executar("INSERT INTO contratos_estado (chave, valor) VALUES (?, ?) "
                            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, str(valor)))


def notas_para_log(c: Contrato) -> str:
    """Notas da entrada no Log do Capitão: tipo, reputação, suas notas e os objetivos da missão."""
    linhas = [" · ".join(t for t in (c.tipo, c.reputacao) if t)]
    if c.notas:
        linhas.append(c.notas)
    if c.objetivos:
        linhas.append("Objetivos:")
        simbolos = {OBJ_FEITO: "✔", OBJ_CANCELADO: "✕"}
        for o in c.objetivos:
            sufixo = " (retirado)" if o.status == OBJ_CANCELADO else ""
            linhas.append(f"{simbolos.get(o.status, '○')} {o.texto or o.id}{sufixo}")
    return "\n".join(l for l in linhas if l)


def resumo(contratos: list[Contrato]) -> dict[str, Any]:
    """Totais do histórico: quantidade, taxa de sucesso e soma das recompensas informadas.

    A taxa considera só desfechos do jogador (concluído, falhou, abandonado); cancelados
    pelo jogo e "sem desfecho no log" ficam de fora.
    """
    concluidos = [c for c in contratos if c.status == CONCLUIDO]
    decididos = [c for c in contratos if c.status in (CONCLUIDO, FALHOU, ABANDONADO)]
    com_valor = [c.recompensa for c in concluidos if c.recompensa]
    return {
        "total": len(contratos),
        "concluidos": len(concluidos),
        "taxa": (len(concluidos) / len(decididos)) if decididos else None,
        "recompensas": sum(com_valor),
        "com_recompensa": len(com_valor),
    }
