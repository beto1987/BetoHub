"""Testes do repositório do Log do Capitão (banco + resumo + CSV)."""

import pytest

from datetime import datetime

from beto_hub.core.database import BancoDados
from plugins.log_capitao.repositorio import (
    MIGRACOES, TIPO_ANOTACAO, TIPO_REFINO, Entrada, RepositorioLog, data_inicial,
)


def test_salvar_listar_editar_excluir_e_resumo(tmp_path):
    banco = BancoDados(tmp_path / "t.db")
    banco.migrar("log_capitao", MIGRACOES)
    repo = RepositorioLog(banco)

    v1 = Entrada(data="2026-11-20 10:00", mercadoria="Laranite", origem="ARC-L1", destino="Port Tressler",
                 scu=100, preco_compra=25.5, preco_venda=31.0)
    v2 = Entrada(data="2026-11-25 21:00", mercadoria="Agricium", scu=50, preco_compra=20, preco_venda=18)
    nota = Entrada(data="2026-11-24 08:00", tipo=TIPO_ANOTACAO, titulo="Pirata em CRU-L1")
    for e in (v1, v2, nota):
        repo.salvar(e)

    todas = repo.listar()
    assert [e.data for e in todas] == ["2026-11-25 21:00", "2026-11-24 08:00", "2026-11-20 10:00"]

    r = repo.resumo(todas)
    assert r["viagens"] == 2
    assert r["lucro_total"] == 550 - 100
    assert r["melhor"].mercadoria == "Laranite"

    v2.preco_venda = 30
    repo.salvar(v2)
    assert repo.listar(desde="2026-11-25 00:00")[0].lucro == 500

    repo.excluir(nota.id)
    assert len(repo.listar()) == 2
    banco.fechar()


def test_periodos():
    agora = datetime(2026, 11, 25, 18, 30)
    assert data_inicial(0, agora) == "2026-11-25 00:00"
    assert data_inicial(7, agora) == "2026-11-19 00:00"
    assert data_inicial(None, agora) is None


def test_exportar_csv_formato_brasileiro(tmp_path):
    caminho = tmp_path / "log.csv"
    RepositorioLog.exportar_csv([Entrada(mercadoria="Titanium", scu=10, preco_compra=8.5, preco_venda=9.75)], caminho)
    texto = caminho.read_text(encoding="utf-8-sig")
    assert texto.splitlines()[0].startswith("Data;Tipo;")
    assert "Titanium" in texto and "12,50" in texto  # lucro 10 × 1,25


def test_refino_no_log_e_migracao_da_versao_1(tmp_path):
    banco = BancoDados(tmp_path / "t.db")
    banco.migrar("log_capitao", MIGRACOES[:1])        # banco antigo (etapa 3)
    repo = RepositorioLog(banco)
    banco.executar("INSERT INTO log_capitao_entradas (data, tipo, mercadoria, scu, preco_compra, preco_venda) "
                   "VALUES ('2026-11-20 10:00', 'comercio', 'Gold', 10, 5, 7)")
    assert banco.migrar("log_capitao", MIGRACOES) == 2  # aplica só a coluna nova
    refino = Entrada(data="2026-11-25 20:00", tipo=TIPO_REFINO, mercadoria="Quantainium", origem="ARC-L1",
                     scu=28.8, preco_venda=90, custo_extra=1500)
    repo.salvar(refino)
    assert refino.investimento == 1500 and refino.lucro == pytest.approx(28.8 * 90 - 1500)
    r = repo.resumo(repo.listar())
    assert (r["operacoes"], r["viagens"], r["refinos"]) == (2, 1, 1)
    assert r["lucro_total"] == pytest.approx(20 + 28.8 * 90 - 1500)
    assert repo.listar()[1].custo_extra == 0  # entrada antiga ganhou o valor padrão
    banco.fechar()


def test_entrada_de_contrato_usa_recompensa_total():
    from plugins.log_capitao.repositorio import TIPO_CONTRATO, Entrada
    e = Entrada(tipo=TIPO_CONTRATO, titulo="Rookie Haul", preco_venda=45000, custo_extra=5000)
    assert (e.tem_valor, e.receita, e.investimento, e.lucro, e.resumo) == (True, 45000, 5000, 40000, "Rookie Haul")
