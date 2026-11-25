"""Testes do Refino: estimativas por método, preços do refinado e pedidos."""

import pytest

from beto_hub.core.database import BancoDados
from plugins.refino.logica.estimativas import (
    Auditoria, Estimador, Item, Metodo, chave_minerio, detectar_unidade, eh_bruto, formatar_minutos,
    minerios_de_uex, precos_refinados, refinarias_de_uex,
)
from plugins.refino.logica.pedidos import ANDAMENTO, MIGRACOES, PRONTO, RETIRADO, Pedido, RepositorioPedidos

METODOS = [Metodo.de_uex({"id": 1, "name": "Dinyx Solventation", "rating_yield": 3, "rating_cost": 1, "rating_speed": 1}),
           Metodo.de_uex({"id": 2, "name": "Cormack", "rating_yield": 1, "rating_cost": 2, "rating_speed": 3}),
           Metodo.de_uex({"id": 3, "name": "Sem relatos"})]

YIELDS = [
    {"id_terminal": 10, "terminal_name": "ARC-L1", "star_system_name": "Stanton", "commodity_name": "Quantainium (Raw)", "value": 10},
    {"id_terminal": 20, "terminal_name": "CRU-L1", "star_system_name": "Stanton", "commodity_name": "Quantainium (Raw)", "value": 0},
    {"id_terminal": 20, "terminal_name": "CRU-L1", "star_system_name": "Stanton", "commodity_name": "Iron (Ore)", "value": -2},
]


def aud(metodo, terminal, minerio, q, r, custo, minutos, bonus):
    return Auditoria.de_uex({"method": metodo, "id_terminal": terminal, "commodity_name": minerio,
                             "quantity": q, "quantity_yield": r, "total_cost": custo,
                             "total_time": minutos, "yield": bonus})


@pytest.fixture
def estimador():
    # Relatos em cSCU (mediana > 400). Método 1: rende 90% base, 1 aUEC e 0,1 min por cSCU.
    auditorias = [aud(1, 20, "Quantainium (Raw)", 1000, 900, 1000, 100, 0) for _ in range(3)]
    auditorias += [aud(2, 20, "Iron (Ore)", 2000, 1000, 500, 20, 0) for _ in range(3)]
    precos = precos_refinados([
        {"commodity_name": "Quantainium", "price_sell": 88.0, "terminal_name": "Area18"},
        {"commodity_name": "Quantainium", "price_sell": 90.0, "terminal_name": "Lorville"},
        {"commodity_name": "Quantainium (Raw)", "price_sell": 500.0, "terminal_name": "X"},  # bruto: ignorado
    ])
    return Estimador(METODOS, auditorias, refinarias_de_uex(YIELDS), precos)


def test_nomes_de_minerio():
    assert eh_bruto("Quantainium (Raw)") and eh_bruto("Iron (Ore)") and not eh_bruto("Quantainium")
    assert chave_minerio("Quantainium (Raw)") == chave_minerio("Quantainium") == "quantainium"
    assert list(minerios_de_uex(YIELDS).values()) == ["Iron", "Quantainium"]


def test_estimativa_aplica_bonus_da_refinaria(estimador):
    item = Item("quantainium", "Quantainium", 3200)  # 32 SCU
    sem_bonus = next(e for e in estimador.estimar(20, [item]) if e.metodo.id == 1)
    com_bonus = next(e for e in estimador.estimar(10, [item]) if e.metodo.id == 1)
    assert sem_bonus.refinado_scu == pytest.approx(32 * 0.9)
    assert com_bonus.refinado_scu == pytest.approx(32 * 0.9 * 1.10)
    assert sem_bonus.custo == pytest.approx(3200) and sem_bonus.minutos == pytest.approx(320)
    assert sem_bonus.valor == pytest.approx(32 * 0.9 * 90)        # melhor preço do refinado
    assert sem_bonus.lucro == pytest.approx(32 * 0.9 * 90 - 3200)
    assert sem_bonus.nivel == "refinaria" and com_bonus.nivel == "minério"


def test_metodos_sem_dados_ficam_por_ultimo(estimador):
    item = Item("quantainium", "Quantainium", 1000)
    estimativas = estimador.estimar(20, [item])
    assert [e.metodo.id for e in estimativas][-1] == 3
    lucros = [e.lucro for e in estimativas if e.lucro is not None]
    assert lucros == sorted(lucros, reverse=True)  # do maior lucro para o menor
    sem = next(e for e in estimador.estimar(20, [item]) if e.metodo.id == 3)
    assert sem.lucro is None and sem.nivel == "sem dados"


def test_varios_minerios_somam_e_usam_nivel_mais_fraco(estimador):
    itens = [Item("quantainium", "Quantainium", 1000), Item("iron", "Iron", 1000)]
    e = next(x for x in estimador.estimar(20, itens) if x.metodo.id == 2)
    assert e.itens[0].nivel == "geral" and e.itens[1].nivel == "refinaria"
    assert e.nivel == "geral"
    assert e.valor is None  # Iron refinado sem preço conhecido -> sem lucro total


def test_unidade_das_auditorias():
    assert detectar_unidade([aud(1, 1, "X", 3200, 1, 1, 1, 0)]) == 1    # cSCU
    assert detectar_unidade([aud(1, 1, "X", 32, 1, 1, 1, 0)]) == 100    # SCU
    assert formatar_minutos(65) == "1 h 05 min" and formatar_minutos(30) == "30 min"
    assert formatar_minutos(60 * 26) == "1 d 2 h" and formatar_minutos(None) == "—"


def test_pedidos_ciclo_de_vida(tmp_path):
    banco = BancoDados(tmp_path / "t.db")
    banco.migrar("refino", MIGRACOES)
    repo = RepositorioPedidos(banco)
    agora = 1_800_000_000.0
    p1 = Pedido("ARC-L1", "Dinyx", minutos=60, custo=1500, inicio=agora - 30 * 60,
                itens=[{"nome": "Quantainium", "chave": "quantainium", "quantidade_cscu": 3200, "refinado_scu": 28.8}],
                valor_estimado=2592)
    p2 = Pedido("CRU-L1", "Cormack", minutos=10, custo=100, inicio=agora - 20 * 60)
    repo.salvar(p1)
    repo.salvar(p2)

    assert p1.restante_s(agora) == pytest.approx(30 * 60)
    assert p1.lucro_estimado == pytest.approx(1092) and p1.refinado_scu == pytest.approx(28.8)
    assert "3.200 cSCU" in p1.descricao_itens

    prontos = repo.marcar_prontos(agora)
    assert [p.id for p in prontos] == [p2.id]
    assert repo.marcar_prontos(agora) == []  # não avisa duas vezes
    assert [p.status for p in repo.listar()] == [PRONTO, ANDAMENTO]  # prontos primeiro

    repo.definir_status(p2.id, RETIRADO)
    assert [p.id for p in repo.listar()] == [p1.id]
    assert len(repo.listar(incluir_retirados=True)) == 2
    repo.excluir(p1.id)
    assert repo.listar() == []
    banco.fechar()
