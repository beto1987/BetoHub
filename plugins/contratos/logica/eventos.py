"""Transforma linhas do Game.log do Star Citizen em eventos de contrato. Sem Qt, testável.

Linhas usadas (formato do jogo 4.x):
  <2026-11-23T23:38:08.317Z> [Notice] <SHUDEvent_OnNotification> Added notification
      "Contract Accepted:  Título <EM4>[100 Rep]</EM4>: " [59] to queue. ... MissionId: [uuid], ObjectiveId: []
  ... Added notification "New Objective: Deliver 0/2 SCU of ... : " ... MissionId: [uuid], ObjectiveId: [dropoff_..._0]
  ... Added notification "Objective Withdrawn: ...", "Contract Complete: ...", "Contract Failed: ...", "Contract Withdrawn: ..."
  <...> [Notice] <ObjectiveUpserted> ... mission_id <uuid> - objective_id <id> - state MISSION_OBJECTIVE_STATE_COMPLETED
  <...> [Notice] <EndMission> Ending mission for player. MissionId[uuid] ... CompletionType[Complete] Reason[...]

A recompensa (aUEC) e o prazo NÃO aparecem no log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

ACEITO, OBJETIVO, OBJ_CONCLUIDO, OBJ_RETIRADO, ENCERRADO, FIM_NOTIFICADO, DEFINICAO = (
    "aceito", "objetivo", "obj_concluido", "obj_retirado", "encerrado", "fim_notificado", "definicao")

# Resultado final do contrato
ATIVO, CONCLUIDO, FALHOU, ABANDONADO, DESATIVADO, SEM_FIM = (
    "ativo", "concluido", "falhou", "abandonado", "desativado", "sem_fim")
NOMES_STATUS = {ATIVO: "Em andamento", CONCLUIDO: "Concluído", FALHOU: "Falhou",
                ABANDONADO: "Abandonado", DESATIVADO: "Cancelado", SEM_FIM: "Sem desfecho no log"}
_RESULTADOS = {"complete": CONCLUIDO, "fail": FALHOU, "abandon": ABANDONADO, "deactivate": DESATIVADO}
_NOTIF_FIM = {"Contract Complete": CONCLUIDO, "Contract Failed": FALHOU, "Contract Withdrawn": DESATIVADO}

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_ZERO = "00000000-0000-0000-0000-000000000000"
_RE_HORA = re.compile(r"^<(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)Z>")
_RE_NOTIF = re.compile(
    r'Added notification "(?P<texto>.*?)" \[\d+\] to queue.*?MissionId: \[(?P<missao>' + _UUID + r')\]'
    r'(?:, ObjectiveId: \[(?P<objetivo>[^\]]*)\])?', re.S)
_RE_UPSERT = re.compile(r"<Objective(?:Upserted|Complete)>.*?mission_id (?P<missao>" + _UUID + r") - objective_id "
                        r"(?P<objetivo>\S+) - state MISSION_OBJECTIVE_STATE_(?P<estado>\w+)")
_RE_FIM = re.compile(r"<EndMission>.*?MissionId\[(?P<missao>" + _UUID + r")\].*?CompletionType\[(?P<tipo>\w+)\]")
_RE_ENFASE = re.compile(r"<EM\d>(.*?)</EM\d>", re.S)
# Nome interno da missão (existe também em versões antigas do jogo, sem as notificações)
_RE_DEFINICAO = re.compile(r"<CLocalMissionPhaseMarker::CreateMarker>.*?missionId \[(?P<missao>" + _UUID +
                           r")\].*?contract \[(?P<contrato>[^\]]+)\]")


@dataclass(frozen=True)
class Evento:
    tipo: str
    missao: str
    quando: float               # epoch (UTC)
    titulo: str = ""
    objetivo: str = ""          # id do objetivo
    texto: str = ""             # texto do objetivo
    resultado: str = ""         # para ENCERRADO / FIM_NOTIFICADO
    reputacao: str = ""         # ex.: "[100 Rep]"


def _hora(linha: str) -> float | None:
    m = _RE_HORA.match(linha)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def limpar_titulo(texto: str) -> tuple[str, str]:
    """("Ling Family Rookie Haul | to Canard View", "[100 Rep] [BP]*") a partir do texto da notificação."""
    reputacao = " ".join(t.strip() for t in _RE_ENFASE.findall(texto) if t.strip())
    titulo = _RE_ENFASE.sub("", texto)
    titulo = re.sub(r"\s+", " ", titulo).strip().rstrip(":").strip()
    return titulo, reputacao


def _linhas_completas(linhas: Iterable[str]) -> Iterable[str]:
    """Junta notificações cujo texto quebrou em várias linhas (até 6)."""
    pendente: list[str] = []
    for linha in linhas:
        linha = linha.rstrip("\r\n")
        if pendente:
            pendente.append(linha)
            if "to queue" in linha or len(pendente) >= 6:
                yield "\n".join(pendente)
                pendente = []
            continue
        if 'Added notification "' in linha and "to queue" not in linha:
            pendente = [linha]
            continue
        yield linha
    if pendente:
        yield "\n".join(pendente)


def analisar(linhas: Iterable[str]) -> list[Evento]:
    """Eventos de contrato, na ordem em que aparecem no log."""
    eventos: list[Evento] = []
    ultima_hora = 0.0
    for linha in _linhas_completas(linhas):
        quando = _hora(linha)
        if quando is None:
            quando = ultima_hora  # continuação de linha: usa a hora anterior
        ultima_hora = quando

        if "Added notification" in linha:
            m = _RE_NOTIF.search(linha)
            if not m or m.group("missao") == _ZERO:
                continue
            texto, missao, objetivo = m.group("texto"), m.group("missao").lower(), (m.group("objetivo") or "").strip()
            tipo, _, resto = texto.partition(":")
            tipo = tipo.strip()
            if tipo == "Contract Accepted":
                titulo, rep = limpar_titulo(resto)
                eventos.append(Evento(ACEITO, missao, quando, titulo=titulo, reputacao=rep))
            elif tipo == "New Objective":
                texto_obj = re.sub(r"\s+", " ", resto).strip().rstrip(":").strip()
                eventos.append(Evento(OBJETIVO, missao, quando, objetivo=objetivo or texto_obj, texto=texto_obj))
            elif tipo == "Objective Withdrawn":
                texto_obj = re.sub(r"\s+", " ", resto).strip().rstrip(":").strip()
                eventos.append(Evento(OBJ_RETIRADO, missao, quando, objetivo=objetivo or texto_obj, texto=texto_obj))
            elif tipo in _NOTIF_FIM:
                titulo, rep = limpar_titulo(resto)
                eventos.append(Evento(FIM_NOTIFICADO, missao, quando, titulo=titulo, reputacao=rep,
                                      resultado=_NOTIF_FIM[tipo]))
            continue

        if "<ObjectiveUpserted>" in linha or "<ObjectiveComplete>" in linha:
            m = _RE_UPSERT.search(linha)
            if m and m.group("estado").upper() == "COMPLETED":
                eventos.append(Evento(OBJ_CONCLUIDO, m.group("missao").lower(), quando, objetivo=m.group("objetivo")))
            continue

        if "<EndMission>" in linha:
            m = _RE_FIM.search(linha)
            if m:
                resultado = _RESULTADOS.get(m.group("tipo").lower(), DESATIVADO)
                eventos.append(Evento(ENCERRADO, m.group("missao").lower(), quando, resultado=resultado))
            continue

        if "<CLocalMissionPhaseMarker::CreateMarker>" in linha:
            m = _RE_DEFINICAO.search(linha)
            if m:
                eventos.append(Evento(DEFINICAO, m.group("missao").lower(), quando, texto=m.group("contrato")))
    return eventos


def nome_legivel(interno: str) -> str:
    """"HaulCargo_MultiToSingle_Interstellar_Small" -> "Haul Cargo · Multi To Single · Interstellar · Small"."""
    partes = []
    for p in (interno or "").split("_"):
        p = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d)", " ", p).strip()
        if p:
            partes.append(p)
    return " · ".join(partes)


# ---------------------------------------------------------------- classificação
_TIPOS = (
    ("Transporte", r"haul|deliver|cargo|courier|delivery|supply|package|transport"),
    ("Salvamento", r"salvage|claim #|debris|wreck"),
    ("Resgate", r"rescue|missing person|distress|medical|medivac|survivor|beacon"),
    ("Mineração", r"\bmining|\bmine\b|\bore\b|asteroid mining|resource ?gathering"),
    ("Caça-recompensa", r"bounty|crimestat|criminal|wanted|\btarget:"),
    ("Combate", r"combat|gauntlet|defeat|eliminate|neutralize|kill|hostile|attack|defend|protect|patrol|interdict|"
                r"xenothreat|assault|ambush|security|escort"),
    ("Investigação", r"investigat|locate|search|blackbox|recover|retrieve|find"),
)


def classificar(titulo: str, objetivos: Iterable[str] = ()) -> str:
    """Tipo do contrato pelo título (e, se precisar, pelos objetivos)."""
    for texto in (titulo, " ".join(objetivos)):
        t = (texto or "").lower()
        for nome, padrao in _TIPOS:
            if re.search(padrao, t):
                return nome
    return "Outros"


def local_do_titulo(titulo: str) -> str:
    """Local citado no título: "... | to Canard View" -> "Canard View"; "... | from ArcCorp Mining Area 056" idem.

    Só olha as partes depois de "|" (padrão do jogo), para não pegar "A Call to Arms".
    """
    for parte in reversed([p.strip() for p in titulo.split("|")[1:]]):
        m = re.match(r"(?:to|from|at)\s+(.+)$", parte, re.I)
        if m:
            return m.group(1).strip()
    return ""
