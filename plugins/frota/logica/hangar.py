"""Naves do jogador (tabela frota_hangar). Sem Qt, testável."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from beto_hub.core.i18n import N_
from beto_hub.core.database import BancoDados

ORIGENS = (N_("Comprada no jogo"), N_("Pledge"), N_("Pledge (seguro vitalício)"), N_("Emprestada (loaner)"),
           N_("Alugada"), N_("Outra"))

MIGRACOES = [
    """
    CREATE TABLE frota_hangar (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid       TEXT NOT NULL,              -- nave na Star Citizen Wiki
        nome       TEXT NOT NULL,              -- nome da nave quando foi adicionada (plano B do uuid)
        apelido    TEXT NOT NULL DEFAULT '',
        origem     TEXT NOT NULL DEFAULT '',
        notas      TEXT NOT NULL DEFAULT '',
        criado_em  TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """,
]


@dataclass
class NaveHangar:
    uuid: str
    nome: str
    apelido: str = ""
    origem: str = ""
    notas: str = ""
    id: int | None = None

    @property
    def rotulo(self) -> str:
        return f"{self.apelido} ({self.nome})" if self.apelido else self.nome

    @classmethod
    def de_linha(cls, l: Any) -> "NaveHangar":
        return cls(id=l["id"], uuid=l["uuid"], nome=l["nome"], apelido=l["apelido"],
                   origem=l["origem"], notas=l["notas"])


class RepositorioHangar:
    def __init__(self, banco: BancoDados):
        self.banco = banco

    def salvar(self, n: NaveHangar) -> int:
        valores = (n.uuid, n.nome, n.apelido.strip(), n.origem, n.notas.strip())
        if n.id is None:
            cur = self.banco.executar(
                "INSERT INTO frota_hangar (uuid, nome, apelido, origem, notas) VALUES (?, ?, ?, ?, ?)", valores)
            n.id = int(cur.lastrowid)
        else:
            self.banco.executar(
                "UPDATE frota_hangar SET uuid=?, nome=?, apelido=?, origem=?, notas=? WHERE id=?", (*valores, n.id))
        return n.id

    def listar(self) -> list[NaveHangar]:
        linhas = self.banco.consultar("SELECT * FROM frota_hangar ORDER BY lower(nome), lower(apelido), id")
        return [NaveHangar.de_linha(l) for l in linhas]

    def obter(self, id_nave: int) -> NaveHangar | None:
        l = self.banco.consultar_um("SELECT * FROM frota_hangar WHERE id=?", (id_nave,))
        return NaveHangar.de_linha(l) if l else None

    def excluir(self, id_nave: int) -> None:
        self.banco.executar("DELETE FROM frota_hangar WHERE id=?", (id_nave,))
