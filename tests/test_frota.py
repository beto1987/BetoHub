"""Testes da Frota: cliente da Star Citizen Wiki, fichas, comparação e hangar — sem rede e sem Qt."""

import pytest

from beto_hub.core.database import BancoDados
from beto_hub.core.texto import chave_nome
from beto_hub.services.api_cache import MIGRACOES_NUCLEO, CacheAPI
from beto_hub.services.http_client import ErroHTTP
from beto_hub.services.wiki_api import ClienteWiki, ErroWiki, resumir_nave
from plugins.frota.logica.comparacao import ATRIBUTOS, melhores, numero
from plugins.frota.logica.hangar import MIGRACOES, NaveHangar, RepositorioHangar
from plugins.frota.logica.naves import FichaNave, encontrar, fichas_de_wiki


def nave_wiki(nome, classe, uuid, **extra):
    """Uma nave no formato da API da Wiki (só o que importa nos testes)."""
    d = {
        "uuid": uuid, "name": nome, "game_name": extra.pop("game_name", nome), "class_name": classe,
        "manufacturer": {"name": "Aegis Dynamics", "code": "AEGS", "uuid": "x", "link": "y"},
        "is_spaceship": True, "is_vehicle": False, "career": "Combat", "role": "Light Fighter",
        "size": {"en_EN": "Small", "de_DE": "Klein"}, "production_status": {"en_EN": "flight-ready"},
        "crew": {"min": 1, "max": 1}, "cargo_capacity": 0, "health": 6110,
        "shield": {"hp": 6336, "regeneration": 1204, "face_type": "Bubble", "resistance": {"muito": "grande"}},
        "armor": {"health": 3300, "deflection": {}},
        "speed": {"scm": 226, "max": 1193, "boost_forward": 520},
        "agility": {"pitch": 70, "yaw": 60, "roll": 200},
        "quantum": {"quantum_speed": 161410900, "quantum_range": 32223415682, "quantum_spool_time": 4.4},
        "weaponry": {
            "pilot_dps": 1944.5, "pilot_sustained_dps": 1186.9, "pilot_alpha": 119.4,
            "fixed_weapons": {"weapons": [
                {"name": "CF-337 Panther Repeater", "dps": 545.6}, {"name": "CF-337 Panther Repeater", "dps": 545.6},
                {"name": "Mantis GT-220 Gatling", "dps": 853.3}]},
            "missiles": {"count": 6}, "total_missile_damage": 12160,
        },
        "insurance": {"claim_time": 5.83, "expedite_time": 1.94, "expedite_cost": 2335},
        "msrp": 90, "version": "4.10.3-LIVE.13165946",
        "uex_prices": {
            "purchase": [
                {"price_buy": 2381400, "terminal_name": "Teach's", "starmap_location": {"star_system_name": "Nyx"}},
                {"price_buy": 2262330, "terminal_name": "New Deal", "starmap_location": {"star_system_name": "Stanton"}},
            ],
            "rental": [],
        },
        "ports": [{"muito": "grande"}] * 50, "images": ["x"] * 10,
    }
    d.update(extra)
    return d


GLADIUS = nave_wiki("Gladius", "AEGS_Gladius", "u-gladius", game_name="Aegis Gladius")


# ---------------------------------------------------------------- cliente da Wiki
class HttpFalso:
    def __init__(self, paginas):
        self.paginas = paginas
        self.chamadas = []
        self.fora_do_ar = False

    def obter_json(self, url, params=None, cabecalhos=None):
        self.chamadas.append((url, dict(params or {})))
        if self.fora_do_ar:
            raise ErroHTTP("sem conexão")
        n = params["page[number]"]
        return {"data": self.paginas[n - 1], "meta": {"last_page": len(self.paginas)}}


@pytest.fixture
def banco(tmp_path):
    b = BancoDados(tmp_path / "t.db")
    b.migrar("nucleo", MIGRACOES_NUCLEO)
    yield b
    b.fechar()


def test_resumir_nave_descarta_campos_pesados():
    r = resumir_nave(GLADIUS)
    assert "ports" not in r and "images" not in r
    assert r["shield"] == {"hp": 6336, "regeneration": 1204, "regeneration_time": None, "face_type": "Bubble"}
    assert r["armor"] == {"health": 3300}
    assert r["uex_prices"]["purchase"][1]["star_system_name"] == "Stanton"


def test_wiki_baixa_todas_as_paginas_e_usa_cache(banco):
    http = HttpFalso([[GLADIUS], [nave_wiki("Arrow", "ANVL_Arrow", "u-arrow")]])
    c = ClienteWiki(http, CacheAPI(banco))
    r1 = c.naves()
    assert [n["name"] for n in r1.dados] == ["Gladius", "Arrow"] and not r1.do_cache
    assert http.chamadas[0][1] == {"page[size]": 50, "page[number]": 1}
    r2 = c.naves()
    assert r2.do_cache and len(http.chamadas) == 2  # nada novo baixado


def test_wiki_fora_do_ar_usa_cache_antigo_ou_falha(banco):
    http = HttpFalso([[GLADIUS]])
    c = ClienteWiki(http, CacheAPI(banco))
    http.fora_do_ar = True
    with pytest.raises(ErroWiki):
        c.naves()
    http.fora_do_ar = False
    c.naves()
    http.fora_do_ar = True
    r = c.naves(forcar=True)
    assert r.desatualizado and r.aviso and r.dados[0]["name"] == "Gladius"


# ---------------------------------------------------------------- fichas
def test_ficha_de_wiki():
    f = FichaNave.de_wiki(resumir_nave(GLADIUS))
    assert (f.nome, f.fabricante, f.carreira_pt, f.tamanho_pt, f.versao) == (
        "Gladius", "Aegis Dynamics", "Combate", "Pequena", "4.10.3")
    assert f.dps_total == 1944.5 and f.hp_total == 6110 + 6336
    assert [(a.nome, a.quantidade) for a in f.armas] == [("CF-337 Panther Repeater", 2), ("Mantis GT-220 Gatling", 1)]
    assert (f.preco_jogo, f.preco_jogo_local) == (2262330, "New Deal (Stanton)")  # o mais barato
    assert f.misseis == 6 and f.aluguel is None
    assert set(f.chaves) == {"gladius", "aegisgladius"}


def test_chaves_sem_fabricante_e_sem_acento():
    f = FichaNave.de_wiki({"uuid": "p", "name": "MISC Prospector", "game_name": "MISC Prospector",
                           "manufacturer": {"name": "Musashi Industrial and Starflight Concern", "code": "MISC"}})
    assert f.nome == "Prospector"  # sem a sigla do fabricante, como as outras naves
    assert set(f.chaves) == {"miscprospector", "prospector"}
    assert chave_nome("Gatac Hyūn") == "gatachyun"


def test_fichas_de_wiki_limpa_maquetes_e_repetidos():
    linhas = [
        GLADIUS,
        nave_wiki("Gladius", "AEGS_Gladius_BIS2950", "u-gladius-bis", game_name="Aegis Gladius"),  # mesma nave
        nave_wiki("Avenger Stalker", "AEGS_Avenger_Stalker_Display", "u-display"),                 # maquete
        nave_wiki("Corsair PYAM Exec", "DRAK_Corsair_Exec_Military", "u-c1", health=1),
        nave_wiki("Corsair PYAM Exec", "DRAK_Corsair_Exec_Stealth", "u-c2", health=2),
    ]
    nomes = [f.nome for f in fichas_de_wiki(linhas)]
    assert nomes == ["Corsair PYAM Exec (Military)", "Corsair PYAM Exec (Stealth)", "Gladius"]
    assert fichas_de_wiki(linhas)[-1].uuid == "u-gladius"  # fica a "original"


def test_encontrar_por_uuid_ou_nome():
    fichas = fichas_de_wiki([GLADIUS, nave_wiki("Arrow", "ANVL_Arrow", "u-arrow")])
    assert encontrar(fichas, uuid="u-arrow").nome == "Arrow"
    assert encontrar(fichas, uuid="uuid-que-mudou", nome="Gladius").uuid == "u-gladius"
    assert encontrar(fichas, uuid="nada", nome="Nave inexistente") is None


# ---------------------------------------------------------------- comparação
def _atributo(rotulo):
    return next(a for a in ATRIBUTOS if a.rotulo == rotulo)


def test_melhores_destaca_maior_ou_menor_e_ignora_empate():
    a = FichaNave(uuid="a", nome="A", dps_piloto=100, quantum_spool=5, escudo_hp=10)
    b = FichaNave(uuid="b", nome="B", dps_piloto=300, quantum_spool=3, escudo_hp=10)
    c = FichaNave(uuid="c", nome="C", dps_piloto=None, quantum_spool=4, escudo_hp=10)
    assert melhores([a, b, c], _atributo("DPS do piloto")) == {1}
    assert melhores([a, b, c], _atributo("Spool")) == {1}        # menor é melhor
    assert melhores([a, b, c], _atributo("Escudo")) == set()     # todos iguais
    assert melhores([a, b], _atributo("Fabricante")) == set()    # texto: não compara
    assert melhores([a], _atributo("DPS do piloto")) == set()    # só uma nave


def test_formatacao():
    assert numero(1944.4) == "1.944"
    assert numero(12345.67, 1) == "12.345,7"
    assert numero(None) == "—"
    f = FichaNave(uuid="g", nome="G", quantum_velocidade=161410900, quantum_alcance=32223415682)
    assert _atributo("Velocidade quantum").texto(f) == "161.411 km/s"
    assert _atributo("Alcance quantum").texto(f) == "32,2 Gm"


# ---------------------------------------------------------------- hangar
def test_hangar_salvar_listar_editar_excluir(banco):
    banco.migrar("frota", MIGRACOES)
    repo = RepositorioHangar(banco)
    a = NaveHangar(uuid="u-gladius", nome="Gladius", apelido=" Vespa ", origem="Pledge")
    repo.salvar(a)
    repo.salvar(NaveHangar(uuid="u-arrow", nome="Arrow"))
    assert [n.rotulo for n in repo.listar()] == ["Arrow", "Vespa (Gladius)"]
    a.notas = "seguro vitalício"
    repo.salvar(a)
    assert repo.obter(a.id).notas == "seguro vitalício"
    repo.excluir(a.id)
    assert [n.nome for n in repo.listar()] == ["Arrow"]
