"""Banco local SQLite (hub.db) compartilhado por todos os módulos.

Regras:
- Cada módulo usa tabelas com o próprio prefixo (comercio_*, frota_*...).
- Cada módulo declara uma lista de migrações SQL; a posição na lista é a
  versão. A tabela `versoes_schema` guarda até onde cada módulo já aplicou.
  Nunca edite uma migração já publicada: acrescente uma nova no fim da lista.
- A conexão é única e protegida por trava, então pode ser usada a partir
  das threads de trabalho.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from beto_hub.core.i18n import tr
from .logging_setup import obter_logger

log = obter_logger("banco")


class ErroMigracao(RuntimeError):
    pass


class BancoDados:
    def __init__(self, caminho: Path | str):
        self.caminho = str(caminho)
        self._trava = threading.RLock()
        # isolation_level=None -> autocommit; transações são abertas explicitamente.
        self._con = sqlite3.connect(self.caminho, check_same_thread=False, isolation_level=None)
        self._con.row_factory = sqlite3.Row
        with self._trava:
            self._con.execute("PRAGMA journal_mode=WAL")
            self._con.execute("PRAGMA foreign_keys=ON")
            self._con.execute("PRAGMA busy_timeout=5000")
            self._con.execute(
                "CREATE TABLE IF NOT EXISTS versoes_schema ("
                " modulo TEXT PRIMARY KEY,"
                " versao INTEGER NOT NULL,"
                " atualizado_em TEXT NOT NULL DEFAULT (datetime('now')))"
            )
        log.info("Banco aberto: %s", self.caminho)

    # ------------------------------------------------------------ consultas
    def executar(self, sql: str, params: Sequence[Any] | dict = ()) -> sqlite3.Cursor:
        with self._trava:
            return self._con.execute(sql, params)

    def executar_varios(self, sql: str, lista: Sequence[Sequence[Any]]) -> None:
        with self.transacao() as con:
            con.executemany(sql, lista)

    def consultar(self, sql: str, params: Sequence[Any] | dict = ()) -> list[sqlite3.Row]:
        with self._trava:
            return self._con.execute(sql, params).fetchall()

    def consultar_um(self, sql: str, params: Sequence[Any] | dict = ()) -> sqlite3.Row | None:
        with self._trava:
            return self._con.execute(sql, params).fetchone()

    @contextmanager
    def transacao(self) -> Iterator[sqlite3.Connection]:
        """Uso: with banco.transacao() as con: con.execute(...)"""
        with self._trava:
            self._con.execute("BEGIN")
            try:
                yield self._con
            except Exception:
                self._con.execute("ROLLBACK")
                raise
            else:
                self._con.execute("COMMIT")

    # ------------------------------------------------------------ migrações
    def versao(self, modulo: str) -> int:
        linha = self.consultar_um("SELECT versao FROM versoes_schema WHERE modulo=?", (modulo,))
        return int(linha["versao"]) if linha else 0

    def migrar(self, modulo: str, migracoes: Sequence[str]) -> int:
        """Aplica as migrações pendentes do módulo. Devolve a versão final.

        Cada migração roda numa transação própria: se falhar, nada dela fica
        gravado e as anteriores continuam valendo.
        """
        atual = self.versao(modulo)
        if atual > len(migracoes):
            log.warning(
                "Banco do módulo %s está na versão %d, mas o código só conhece %d.",
                modulo, atual, len(migracoes),
            )
            return atual

        for numero in range(atual + 1, len(migracoes) + 1):
            sql = migracoes[numero - 1]
            log.info("Módulo %s: aplicando migração %d", modulo, numero)
            with self._trava:
                try:
                    # executescript não aceita parâmetros; o id do módulo já foi
                    # validado pelo carregador (só [a-z0-9_]), e a versão é int.
                    self._con.executescript(
                        "BEGIN;\n"
                        f"{sql}\n;\n"
                        "INSERT INTO versoes_schema (modulo, versao) "
                        f"VALUES ('{modulo}', {int(numero)}) "
                        "ON CONFLICT(modulo) DO UPDATE SET versao=excluded.versao, "
                        "atualizado_em=datetime('now');\n"
                        "COMMIT;"
                    )
                except sqlite3.Error as erro:
                    if self._con.in_transaction:
                        self._con.execute("ROLLBACK")
                    raise ErroMigracao(
                        tr("Falha na migração {numero} do módulo '{modulo}': {erro}", numero=numero,
                           modulo=modulo, erro=erro)
                    ) from erro
        return len(migracoes)

    def fechar(self) -> None:
        with self._trava:
            try:
                self._con.close()
                log.info("Banco fechado")
            except sqlite3.Error:
                log.exception("Erro ao fechar o banco")
