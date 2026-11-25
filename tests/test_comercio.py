"""Testes da lógica do Comércio (rotas, eficiência, risco) — sem rede e sem Qt."""

import time

import pytest

from plugins.comercio.logica.modelos import Nave, ParametrosBusca, Preco, Terminal
from plugins.comercio.logica.risco import avaliar_risco
from plugins.comercio.logica.rotas import aplicar_distancias, calcular_rotas, ordenar

AGORA = 1_800_000_000


def term(id_, sistema="Stanton", **extra):
    base = dict(id=id_, name=f"T{id_}", nickname=f"T{id_}", star_system_name=sistema,
                id_space_station=1, is_available_live=1)
    base.update(extra)
    return Terminal.de_uex(base)


def preco(merc, terminal, compra=0, venda=0, estoque=None, idade_h=1):
    return Preco.de_uex(dict(
        id_commodity=merc, commodity_name=f"M{merc}", id_terminal=terminal,
        price_buy=compra, price_sell=venda, scu_buy=estoque,
        date_modified=AGORA - idade_h * 3600,
    ))


@pytest.fixture
def mundo():
    terminais = {t.id: t for t in [
        term(1), term(2), term(3, id_space_station=0, id_outpost=5),
        term(4, sistema="Pyro"), term(5, is_player_owned=1), term(6, is_available_live=0),
    ]}
    precos = [
        preco(10, 1, compra=10, estoque=1000),
        preco(10, 2, venda=15),
        preco(10, 3, venda=18),
        preco(10, 4, venda=40),     # Pyro: muito lucro, mas outro sistema
        preco(10, 5, venda=50),     # terminal de jogador
        preco(10, 6, venda=60),     # terminal indisponível
        preco(20, 2, compra=100, estoque=5),
        preco(20, 1, venda=90),     # prejuízo: não pode aparecer
    ]
    return terminais, precos


def test_quantidade_limitada_pela_nave_capital_e_estoque(mundo):
    terminais, precos = mundo
    r = calcular_rotas(precos, terminais, ParametrosBusca(scu=100, capital=1_000_000))
    melhor = r[0]
    assert (melhor.origem.id, melhor.destino.id, melhor.scu, melhor.limitado_por) == (1, 3, 100, "nave")
    assert melhor.lucro == 800 and melhor.investimento == 1000

    r = calcular_rotas(precos, terminais, ParametrosBusca(scu=100, capital=505))
    assert r[0].scu == 50 and r[0].limitado_por == "capital"

    r = calcular_rotas(precos, terminais, ParametrosBusca(scu=5000, capital=1e9))
    assert r[0].scu == 1000 and r[0].limitado_por == "estoque"


def test_filtros_de_sistema_jogador_e_disponibilidade(mundo):
    terminais, precos = mundo
    destinos = {r.destino.id for r in calcular_rotas(precos, terminais, ParametrosBusca(100, 1e6))}
    assert destinos == {2, 3}  # sem Pyro, sem jogador, sem indisponível, sem prejuízo

    p = ParametrosBusca(100, 1e6, entre_sistemas=True, ignorar_jogadores=False)
    destinos = {r.destino.id for r in calcular_rotas(precos, terminais, p)}
    assert destinos == {2, 3, 4, 5}

    p = ParametrosBusca(100, 1e6, id_origem=2)
    assert calcular_rotas(precos, terminais, p) == []  # origem 2 só vende M20 com prejuízo


def test_eficiencia_usa_distancia_minima(mundo):
    terminais, precos = mundo
    rotas = calcular_rotas(precos, terminais, ParametrosBusca(100, 1e6))
    dist = {(1, 3): 40.0, (3, 1): 40.0, (1, 2): 0.05, (2, 1): 0.05}
    aplicar_distancias(rotas, dist, distancia_minima=1.0, agora=AGORA)
    por_destino = {r.destino.id: r for r in rotas}
    assert por_destino[3].eficiencia == pytest.approx(800 / 40)
    assert por_destino[2].eficiencia == pytest.approx(500 / 1.0)  # 0,05 Gm vira 1 Gm
    assert [r.destino.id for r in ordenar(rotas, "eficiencia")] == [2, 3]
    assert [r.destino.id for r in ordenar(rotas, "lucro")] == [3, 2]


def test_rota_sem_distancia_fica_por_ultimo(mundo):
    terminais, precos = mundo
    rotas = aplicar_distancias(calcular_rotas(precos, terminais, ParametrosBusca(100, 1e6)), {}, agora=AGORA)
    assert all(r.eficiencia is None for r in rotas)
    assert len(ordenar(rotas, "eficiencia")) == len(rotas)


def test_risco_por_criterio():
    seguro = term(1)
    pyro = term(4, sistema="Pyro", is_nqa=1, id_space_station=0, id_outpost=9)

    from plugins.comercio.logica.modelos import Rota
    def rota(origem, destino, scu=10, preco_compra=100, idade_h=1, dist=1.0):
        r = Rota(1, "X", origem, destino, preco_compra, preco_compra * 2, scu, "nave",
                 AGORA - idade_h * 3600, AGORA - idade_h * 3600, distancia=dist)
        return avaliar_risco(r, AGORA)

    nota, nivel, motivos = rota(seguro, term(2))
    assert nivel == "baixo" and nota <= 5

    nota, nivel, motivos = rota(seguro, pyro, scu=50_000, preco_compra=100, idade_h=30, dist=60)
    assert nivel == "alto" and nota == 100
    texto = " ".join(motivos)
    for trecho in ("Pyro", "ponto de salto", "NQA", "outpost", "Gm", "30 h", "carga"):
        assert trecho in texto


def test_ordenar_por_risco_nos_dois_sentidos(mundo):
    terminais, precos = mundo
    p = ParametrosBusca(100, 1e6, entre_sistemas=True)
    rotas = aplicar_distancias(calcular_rotas(precos, terminais, p), {}, agora=AGORA)
    menor = ordenar(rotas, "risco_menor")
    maior = ordenar(rotas, "risco_maior")
    assert menor[0].risco <= menor[-1].risco
    assert maior[0].risco >= maior[-1].risco
    assert maior[0].destino.sistema == "Pyro"


def test_modelos_toleram_campos_ausentes():
    t = Terminal.de_uex({"id": "7"})
    assert t.id == 7 and t.disponivel and t.tipo_local == "superfície"
    p = Preco.de_uex({"id_commodity": 1, "id_terminal": 7, "price_buy": None, "price_sell": "12.5"})
    assert p.compra is None and p.venda == 12.5 and p.estoque_compra is None
    assert Nave.de_uex({"id": 3, "name": "Freelancer", "scu": "66"}).rotulo == "Freelancer (66 SCU)"
