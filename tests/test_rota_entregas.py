"""Testes do planejador de rota das entregas (Contratos) — sem rede e sem Qt."""

import itertools

from plugins.contratos.logica.repositorio import OBJ_ATIVO, OBJ_FEITO, Contrato, Objetivo
from plugins.contratos.logica.rota import (
    COLETA, ENTREGA, IndiceLocais, Local, Parada, ler_entrega, melhor_rota, paradas_dos_contratos,
)

TERMINAIS = [
    {"id": 99, "type": "item", "displayname": "HUR-L1 Green Glade Station", "space_station_name": "HUR-L1 Green Glade Station",
     "star_system_name": "Stanton"},
    {"id": 44, "type": "commodity", "displayname": "HUR-L1 Green Glade Station",
     "space_station_name": "HUR-L1 Green Glade Station", "star_system_name": "Stanton"},
    {"id": 25, "type": "commodity", "displayname": "Everus Harbor", "space_station_name": "Everus Harbor",
     "star_system_name": "Stanton"},
    {"id": 66, "type": "commodity", "displayname": "Port Tressler", "space_station_name": "Port Tressler",
     "star_system_name": "Stanton"},
    {"id": 8, "type": "commodity", "name": "ArcCorp Mining Area 056", "displayname": "ArcCorp Mining Area 056",
     "outpost_name": "ArcCorp Mining Area 056", "star_system_name": "Stanton"},
    {"id": 778, "type": "commodity", "displayname": "Levski", "city_name": "Levski", "star_system_name": "Nyx"},
    {"id": 5, "type": "commodity", "displayname": "Velha", "is_available_live": 0},
]
IDX = IndiceLocais(TERMINAIS)
L = {n: IDX.casar(n) for n in ("HUR-L1 Green Glade Station", "Everus Harbor", "Port Tressler", "ArcCorp Mining Area 056", "Levski")}
DIST = {(25, 44): 1, (44, 66): 39, (25, 66): 38, (8, 44): 20, (8, 25): 21, (8, 66): 45}


def dist(a, b):
    return DIST.get(tuple(sorted((a, b))))


def test_ler_entrega():
    assert ler_entrega("Deliver 2/8 SCU of Iron to HUR-L1 Green Glade Station") == {
        "carga": "Iron", "falta": 6, "destino": "HUR-L1 Green Glade Station"}
    assert ler_entrega("Deliver 0/3 Cargo Boxes to Levski")["destino"] == "Levski"
    assert ler_entrega("Deliver Gold Box To RSI Event Platform")["destino"] == "RSI Event Platform"
    assert ler_entrega("Deliver Data Drive") is None
    assert ler_entrega("Defeat Hostile Ships") is None


def test_indice_casa_nomes_e_escolhe_terminal_de_commodities():
    assert L["HUR-L1 Green Glade Station"] == Local("HUR-L1 Green Glade Station", 44, "Stanton")
    assert IDX.casar("levski").sistema == "Nyx"
    assert IDX.casar("Pyro System") is None
    assert IDX.casar("Velha") is None                     # terminal fora do jogo (is_available_live = 0)


def _contrato(missao, titulo, objetivos):
    return Contrato(missao, titulo=titulo, objetivos=[Objetivo(f"o{i}", t, s) for i, (t, s) in enumerate(objetivos)])


def test_paradas_dos_contratos():
    contratos = [
        _contrato("m1", "Rookie | Interstellar Large Haul | from ArcCorp Mining Area 056", [
            ("Deliver 0/8 SCU of Iron to HUR-L1 Green Glade Station", OBJ_ATIVO),
            ("Deliver 0/4 SCU of Stims to Pyro System", OBJ_ATIVO)]),
        _contrato("m2", "Ling Haul | to Everus Harbor", [
            ("Deliver 2/2 SCU of Food to Everus Harbor", OBJ_ATIVO),     # já completo: fora
            ("Deliver 1/3 SCU of Quartz to Everus Harbor", OBJ_ATIVO),
            ("Deliver 0/1 SCU of Copper to Port Tressler", OBJ_FEITO)]),  # concluído: fora
        _contrato("m3", "Bounty | Target: Fulano", [("Defeat Hostile Ships", OBJ_ATIVO)]),  # não é entrega
    ]
    p = paradas_dos_contratos(contratos, IDX)
    assert [(x.tipo, x.missao, x.texto_local, x.scu) for x in p] == [
        (COLETA, "m1", "ArcCorp Mining Area 056", None),
        (ENTREGA, "m1", "HUR-L1 Green Glade Station", 8),
        (ENTREGA, "m1", "Pyro System", 4),
        (ENTREGA, "m2", "Everus Harbor", 2),
    ]
    assert p[2].local is None and p[2].sistema_sugerido == "Pyro"   # genérico: o jogador escolhe
    assert p[0].local.id_terminal == 8 and p[3].descricao == "Entregar 2 SCU de Quartz"


def _entrega(missao, local, tipo=ENTREGA):
    return Parada(tipo, missao, f"Contrato {missao}", local.nome, "carga", 1, local=local)


def test_melhor_rota_respeita_coleta_antes_da_entrega():
    paradas = [
        _entrega("a", L["Port Tressler"]),
        _entrega("b", L["Everus Harbor"]),
        _entrega("b", L["Port Tressler"], COLETA),     # coleta de "b" em Port Tressler
        _entrega("c", L["HUR-L1 Green Glade Station"]),
    ]
    r = melhor_rota(paradas, dist, inicio=L["ArcCorp Mining Area 056"])
    nomes = [t.local.nome for t in r.trechos]
    assert nomes.index("Port Tressler") < nomes.index("Everus Harbor")
    assert len(r.trechos) == 3                          # duas paradas em Port Tressler viram uma
    assert [p.tipo for p in r.trechos[nomes.index("Port Tressler")].paradas] == [COLETA, ENTREGA]
    # confere com força bruta
    ids = [L[n].id_terminal for n in ("Port Tressler", "Everus Harbor", "HUR-L1 Green Glade Station")]
    validas = [p for p in itertools.permutations(ids) if p.index(66) < p.index(25)]
    melhor = min(sum(dist(a, b) for a, b in zip((8,) + p, p)) for p in validas)
    assert r.total_gm == melhor and r.desconhecidas == 0


def test_rota_sem_inicio_e_com_distancia_desconhecida():
    paradas = [_entrega("a", L["Everus Harbor"]), _entrega("b", L["Levski"]),
               Parada(ENTREGA, "c", "C", "Pyro System", "x", 1)]          # sem local: fica de fora
    r = melhor_rota(paradas, dist)
    assert r.trechos[0].distancia is None                # sem partida: o primeiro trecho não conta
    assert r.desconhecidas == 1 and r.total_gm == 0
    assert any("sem local" in a for a in r.avisos) and any("sem distância" in a for a in r.avisos)


def test_paradas_desmarcadas_ficam_de_fora():
    paradas = [_entrega("a", L["Everus Harbor"]), _entrega("b", L["Port Tressler"])]
    paradas[1].incluir = False
    assert [t.local.nome for t in melhor_rota(paradas, dist).trechos] == ["Everus Harbor"]


def test_lista_de_locais_usa_nome_do_lugar():
    idx = IndiceLocais([{"id": 7, "type": "commodity", "displayname": "TDD Area 18", "city_name": "Area18",
                         "star_system_name": "Stanton"}])
    assert [l.nome for l in idx.todos()] == ["Area18"]
    assert idx.casar("TDD Area 18").id_terminal == idx.casar("Area18").id_terminal == 7
