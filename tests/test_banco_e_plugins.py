"""Testes do banco (migrações) e do carregador de plugins — sem interface gráfica."""

import textwrap

import pytest

from beto_hub.core.database import BancoDados, ErroMigracao
from beto_hub.core.plugin_base import API_VERSAO, ErroManifesto, Manifesto
from beto_hub.core.plugin_loader import DESATIVADO, ERRO, OK, CarregadorPlugins


# ------------------------------------------------------------------ banco
def test_migracoes_incrementais(tmp_path):
    banco = BancoDados(tmp_path / "t.db")
    v1 = ["CREATE TABLE teste_a (id INTEGER PRIMARY KEY, nome TEXT)"]
    assert banco.migrar("teste", v1) == 1
    assert banco.migrar("teste", v1) == 1  # rodar de novo não reaplica

    v2 = v1 + ["ALTER TABLE teste_a ADD COLUMN valor REAL; CREATE INDEX ix_teste ON teste_a(nome)"]
    assert banco.migrar("teste", v2) == 2
    banco.executar("INSERT INTO teste_a (nome, valor) VALUES (?, ?)", ("x", 1.5))
    assert banco.consultar_um("SELECT valor FROM teste_a")["valor"] == 1.5
    banco.fechar()


def test_migracao_com_erro_nao_avanca_versao(tmp_path):
    banco = BancoDados(tmp_path / "t.db")
    banco.migrar("teste", ["CREATE TABLE teste_a (id INTEGER)"])
    with pytest.raises(ErroMigracao):
        banco.migrar("teste", ["CREATE TABLE teste_a (id INTEGER)", "ISTO NÃO É SQL"])
    assert banco.versao("teste") == 1
    banco.fechar()


def test_transacao_desfaz_em_erro(tmp_path):
    banco = BancoDados(tmp_path / "t.db")
    banco.migrar("teste", ["CREATE TABLE teste_a (id INTEGER)"])
    with pytest.raises(RuntimeError):
        with banco.transacao() as con:
            con.execute("INSERT INTO teste_a VALUES (1)")
            raise RuntimeError("falhou no meio")
    assert banco.consultar("SELECT * FROM teste_a") == []
    banco.fechar()


# ------------------------------------------------------------------ manifesto
def test_manifesto_valido(tmp_path):
    m = Manifesto.de_dict({"id": "comercio", "nome": "Comércio", "versao": "1.0", "ordem": 5}, tmp_path)
    assert (m.id, m.ordem, m.classe) == ("comercio", 5, "Plugin")


@pytest.mark.parametrize("dados", [
    {"nome": "X", "versao": "1"},                              # sem id
    {"id": "Comercio", "nome": "X", "versao": "1"},            # maiúscula
    {"id": "a-b", "nome": "X", "versao": "1"},                 # hífen
    {"id": "ok_id", "nome": "X", "versao": "1", "ordem": "x"}, # ordem não numérica
    {"id": "ok_id", "nome": "X", "versao": "1", "api_minima": API_VERSAO + 1},
])
def test_manifesto_invalido(tmp_path, dados):
    with pytest.raises(ErroManifesto):
        Manifesto.de_dict(dados, tmp_path)


# ------------------------------------------------------------------ carregador
def _criar_plugin(raiz, pasta, manifesto, codigo):
    d = raiz / pasta
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("")
    (d / "manifest.toml").write_text(textwrap.dedent(manifesto), encoding="utf-8")
    (d / "plugin.py").write_text(textwrap.dedent(codigo), encoding="utf-8")


def test_carregador_isola_erros(tmp_path):
    raiz = tmp_path / "plugins_teste"
    raiz.mkdir()
    (raiz / "__init__.py").write_text("")
    base = "from beto_hub.core.plugin_base import BasePlugin\n"

    _criar_plugin(raiz, "bom", 'id="bom"\nnome="Bom"\nversao="1"\nordem=2\n',
                  base + "class Plugin(BasePlugin):\n    def migracoes(self): return ['CREATE TABLE bom_x (id INTEGER)']\n")
    _criar_plugin(raiz, "quebrado", 'id="quebrado"\nnome="Quebrado"\nversao="1"\nordem=1\n',
                  "raise ImportError('dependência faltando')\n")
    _criar_plugin(raiz, "sem_classe", 'id="sem_classe"\nnome="Sem"\nversao="1"\n', "x = 1\n")
    _criar_plugin(raiz, "desligado", 'id="desligado"\nnome="Desligado"\nversao="1"\n', base)
    _criar_plugin(raiz, "manifesto_ruim", 'id = = "x"\n', base)

    banco = BancoDados(tmp_path / "t.db")
    contextos = []
    carregador = CarregadorPlugins(raiz, desativados=["desligado"])
    resultado = carregador.carregar_todos(lambda m: contextos.append(m.id) or object(), banco.migrar)
    estados = {p.id: p.estado for p in resultado}

    assert estados == {
        "bom": OK, "quebrado": ERRO, "sem_classe": ERRO,
        "desligado": DESATIVADO, "manifesto_ruim": ERRO,
    }
    assert contextos == ["bom"]
    assert banco.versao("bom") == 1
    assert [p.id for p in resultado][:2] == ["quebrado", "bom"]  # ordenado por "ordem"
    assert "dependência faltando" in next(p for p in resultado if p.id == "quebrado").erro
    banco.fechar()
