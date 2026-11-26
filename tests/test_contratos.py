"""Testes dos Contratos: leitura do Game.log, eventos, banco idempotente — sem Qt e sem o jogo."""

import os
import time

import pytest

from beto_hub.core.database import BancoDados
from plugins.contratos.logica.arquivos import LeitorGameLog, backups
from plugins.contratos.logica.eventos import (
    ABANDONADO, ACEITO, CONCLUIDO, DEFINICAO, ENCERRADO, FALHOU, FIM_NOTIFICADO, OBJ_CONCLUIDO, OBJ_RETIRADO, OBJETIVO,
    SEM_FIM, analisar, classificar, limpar_titulo, local_do_titulo, nome_legivel,
)
from plugins.contratos.logica.repositorio import MIGRACOES, OBJ_CANCELADO, OBJ_FEITO, RepositorioContratos, resumo

M1 = "59aee6b9-9f53-46a0-a56e-e2b0076b58f5"
M2 = "31f5aaad-1bca-48fd-8b93-6ec4a0b8ac49"
ZERO = "00000000-0000-0000-0000-000000000000"
TAG = "[Team_CoreGameplayFeatures][Missions][Comms]"


def notif(hora, texto, missao, objetivo=""):
    return (f'<2026-11-23T{hora}.317Z> [Notice] <SHUDEvent_OnNotification> Added notification "{texto}: " [59] '
            f"to queue. New queue size: 3, MissionId: [{missao}], ObjectiveId: [{objetivo}] {TAG}")


def upsert(hora, missao, objetivo):
    return (f"<2026-11-23T{hora}.378Z> [Notice] <ObjectiveUpserted> Received ObjectiveUpserted push message for: "
            f"mission_id {missao} - objective_id {objetivo} - state MISSION_OBJECTIVE_STATE_COMPLETED - created 0 - "
            f"flags=ShowInLog| [Team_GameServices][Missions]")


def fim(hora, missao, tipo):
    return (f"<2026-11-23T{hora}.481Z> [Notice] <EndMission> Ending mission for player. MissionId[{missao}] "
            f"Player[Alguem] PlayerId[1] CompletionType[{tipo}] Reason[Mission Ended] [Team_MissionFeatures][Missions]")


SESSAO = [
    "<2026-11-23T23:30:00.000Z> [Notice] <Legacy login response> qualquer coisa",
    (f"<2026-11-23T23:38:08.307Z> [Notice] <CLocalMissionPhaseMarker::CreateMarker> Creating objective marker: "
     f"missionId [{M1}], generator name [LingFamilyHauling_Hauling], contract [HaulCargo_MultiToSingle_Small], "
     f"contractDefinitionId[8f29], objectiveId [dropoff_a_0] [Team_MissionFeatures][Missions]"),
    notif("23:38:08", "Contract Accepted:  Ling Family Rookie Haul | to Canard View <EM4>[100 Rep] [BP]*</EM4>", M1),
    notif("23:38:08", "New Objective: Deliver 0/2 SCU of Souvenirs to Pyro System", M1, "dropoff_a_0"),
    notif("23:38:09", "New Objective: Deliver 0/4 SCU of Processed Food to Pyro System", M1, "dropoff_a_1"),
    notif("23:39:00", "Entered Monitored Space", ZERO),          # não é de missão: ignorada
    upsert("23:50:00", M1, "dropoff_a_0"),
    notif("23:51:00", "Objective Withdrawn: Deliver 0/4 SCU of Processed Food to Pyro System", M1, "dropoff_a_1"),
    # notificação quebrada em duas linhas
    '<2026-11-23T23:52:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted:  Bounty',
    f'Hunter | Target: Fulano: " [70] to queue. New queue size: 1, MissionId: [{M2}], ObjectiveId: [] {TAG}',
    fim("23:59:00", M1, "Complete"),
    notif("23:59:00", "Contract Complete:  Ling Family Rookie Haul | to Canard View <EM4>[100 Rep] [BP]*</EM4>", M1),
    fim("23:59:30", M2, "Fail"),
]


# ---------------------------------------------------------------- eventos
def test_analisar_sessao():
    ev = analisar(SESSAO)
    assert [e.tipo for e in ev] == [DEFINICAO, ACEITO, OBJETIVO, OBJETIVO, OBJ_CONCLUIDO, OBJ_RETIRADO, ACEITO,
                                    ENCERRADO, FIM_NOTIFICADO, ENCERRADO]
    aceito = ev[1]
    assert (aceito.missao, aceito.titulo, aceito.reputacao) == (M1, "Ling Family Rookie Haul | to Canard View",
                                                               "[100 Rep] [BP]*")
    assert ev[2].texto == "Deliver 0/2 SCU of Souvenirs to Pyro System" and ev[2].objetivo == "dropoff_a_0"
    assert ev[6].titulo == "Bounty Hunter | Target: Fulano" and ev[6].missao == M2   # linhas juntadas
    assert (ev[7].resultado, ev[9].resultado) == (CONCLUIDO, FALHOU)
    assert ev[1].quando == pytest.approx(time.mktime((2026, 11, 23, 23, 38, 8, 0, 0, 0)) - time.timezone, abs=1)


def test_textos_auxiliares():
    assert limpar_titulo("  Haul | to X <EM4>[50 Rep]</EM4>: ") == ("Haul | to X", "[50 Rep]")
    assert local_do_titulo("Ling Family Rookie Haul | to Canard View") == "Canard View"
    assert local_do_titulo("Rookie | Interstellar Large Haul | from ArcCorp Mining Area 056") == "ArcCorp Mining Area 056"
    assert local_do_titulo("A Call to Arms") == ""
    assert nome_legivel("HaulCargo_MultiToSingle_Stanton4") == "Haul Cargo · Multi To Single · Stanton 4"
    assert classificar("Ling Family Rookie Haul") == "Transporte"
    assert classificar("Claim #36446: Aegis Gladius Salvage Rights") == "Salvamento"
    assert classificar("RSI Ship Under Attack") == "Combate"
    assert classificar("Combat Gauntlet - Scenario #5", ["Go to Asteroid Mining Base"]) == "Combate"
    assert classificar("Algo estranho", ["Locate CrimeStat rated criminals"]) == "Caça-recompensa"
    assert classificar("???") == "Outros"


# ---------------------------------------------------------------- banco
@pytest.fixture
def repo(tmp_path):
    b = BancoDados(tmp_path / "t.db")
    b.migrar("contratos", MIGRACOES)
    yield RepositorioContratos(b)
    b.fechar()


def test_aplicar_e_idempotencia(repo):
    encerradas = repo.aplicar(analisar(SESSAO))
    assert sorted(encerradas) == sorted([M1, M2])
    assert repo.aplicar(analisar(SESSAO)) == []          # mesma sessão de novo (ex.: pelo backup)
    c = repo.obter(M1)
    assert (c.status, c.tipo, c.titulo, c.nome_interno) == (
        CONCLUIDO, "Transporte", "Ling Family Rookie Haul | to Canard View", "HaulCargo_MultiToSingle_Small")
    # concluído: o objetivo restante vira feito; o retirado continua retirado
    assert [o.status for o in c.objetivos] == [OBJ_FEITO, OBJ_CANCELADO]
    assert c.progresso == (1, 1)
    assert repo.obter(M2).status == FALHOU and repo.ativos() == []
    assert len(repo.historico()) == 2


def test_notas_para_log_incluem_objetivos(repo):
    from plugins.contratos.logica.repositorio import notas_para_log
    repo.aplicar(analisar(SESSAO))
    repo.salvar_detalhes(M1, 45000, "pagou bem")
    assert notas_para_log(repo.obter(M1)) == (
        "Transporte · [100 Rep] [BP]*\n"
        "pagou bem\n"
        "Objetivos:\n"
        "✔ Deliver 0/2 SCU of Souvenirs to Pyro System\n"
        "✕ Deliver 0/4 SCU of Processed Food to Pyro System (retirado)")


def test_contrato_ativo_e_detalhes(repo):
    repo.aplicar(analisar(SESSAO[:5]))
    [c] = repo.ativos()
    assert c.progresso == (0, 2) and c.duracao_s > 0
    repo.salvar_detalhes(M1, 45000, "  boa  ")
    repo.encerrar_manual(M1, ABANDONADO)
    c = repo.obter(M1)
    assert (c.recompensa, c.notas, c.status) == (45000, "boa", ABANDONADO)
    repo.excluir(M1)
    assert repo.obter(M1) is None


def test_parados_viram_sem_desfecho_e_ainda_podem_encerrar(repo):
    repo.aplicar(analisar(SESSAO[:5]))
    assert repo.encerrar_parados(agora=time.time() + 4 * 86400) == 1
    assert repo.obter(M1).status == SEM_FIM
    repo.aplicar(analisar(SESSAO))                         # o fim aparece depois (ex.: log antigo importado)
    assert repo.obter(M1).status == CONCLUIDO


def test_resumo():
    from plugins.contratos.logica.repositorio import Contrato
    lista = [Contrato("a", status=CONCLUIDO, recompensa=1000), Contrato("b", status=CONCLUIDO),
             Contrato("c", status=FALHOU), Contrato("d", status=SEM_FIM)]
    r = resumo(lista)
    assert (r["total"], r["concluidos"], r["recompensas"], r["com_recompensa"]) == (4, 2, 1000, 1)
    assert r["taxa"] == pytest.approx(2 / 3)               # "sem desfecho" fica fora da taxa


# ---------------------------------------------------------------- arquivos
def test_leitor_le_so_o_novo_e_detecta_sessao_nova(tmp_path):
    estado: dict[str, str] = {}
    leitor = LeitorGameLog(tmp_path, lambda k, d="": estado.get(k, d), lambda k, v: estado.__setitem__(k, str(v)))
    assert leitor.ler_novidades().linhas == []             # ainda não existe

    log = tmp_path / "Game.log"
    log.write_bytes(b"<cabecalho sessao 1>\nlinha 1\nlinha pela met")
    r = leitor.ler_novidades()
    assert r.linhas == ["<cabecalho sessao 1>", "linha 1"] and r.sessao_nova
    with open(log, "ab") as f:
        f.write(b"ade\nlinha 2\n")
    assert leitor.ler_novidades().linhas == ["linha pela metade", "linha 2"]
    assert leitor.ler_novidades().linhas == []

    log.write_bytes(b"<cabecalho sessao 2>\nnova\n")       # jogo reaberto: arquivo recriado
    r = leitor.ler_novidades()
    assert r.sessao_nova and r.linhas == ["<cabecalho sessao 2>", "nova"]


def test_backups_ordenados_e_filtrados(tmp_path):
    pasta = tmp_path / "logbackups"
    pasta.mkdir()
    agora = time.time()
    for i, nome in enumerate(["Game Build(1) a.log", "Game Build(1) b.log", "PSOCacheGen.log"]):
        p = pasta / nome
        p.write_text("x")
        os.utime(p, (agora - 100 + i, agora - 100 + i))
    assert [p.name for p in backups(tmp_path)] == ["Game Build(1) a.log", "Game Build(1) b.log"]
    assert [p.name for p in backups(tmp_path, desde_mtime=agora - 100)] == ["Game Build(1) b.log"]
