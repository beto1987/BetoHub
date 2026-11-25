"""Testes do cliente UEX com um servidor falso (sem rede)."""

import pytest

from beto_hub.core.database import BancoDados
from beto_hub.services.api_cache import MIGRACOES_NUCLEO, CacheAPI
from beto_hub.services.http_client import ErroHTTP
from beto_hub.services.uex_api import ClienteUEX, ErroUEX


class HttpFalso:
    def __init__(self):
        self.chamadas: list[str] = []
        self.fora_do_ar = False
        self.url_que_funciona = "https://api.uexcorp.uk/2.0"

    def obter_json(self, url, params=None, cabecalhos=None):
        self.chamadas.append(url)
        if self.fora_do_ar or not url.startswith(self.url_que_funciona):
            raise ErroHTTP("sem conexão")
        if url.endswith("/terminals_distances"):
            a, b = params["id_terminal_origin"], params["id_terminal_destination"]
            return {"status": "ok", "data": {"distance": float(a + b)}}
        return {"status": "ok", "data": [{"id": 1, "url": url, "auth": (cabecalhos or {}).get("Authorization")}]}


@pytest.fixture
def cliente(tmp_path):
    banco = BancoDados(tmp_path / "t.db")
    banco.migrar("nucleo", MIGRACOES_NUCLEO)
    http = HttpFalso()
    cfg = {"api.uex_url": "https://api.uexcorp.uk/2.0", "api.uex_token": "abc"}
    c = ClienteUEX(http, CacheAPI(banco), lambda k, d=None: cfg.get(k, d))
    yield c, http, cfg
    banco.fechar()


def test_cache_evita_nova_chamada_e_envia_token(cliente):
    c, http, _ = cliente
    r1 = c.precos_todos()
    r2 = c.precos_todos()
    assert not r1.do_cache and r2.do_cache
    assert len(http.chamadas) == 1
    assert r1.dados[0]["auth"] == "Bearer abc"
    c.precos_todos(forcar=True)
    assert len(http.chamadas) == 2


def test_api_fora_do_ar_usa_cache_antigo(cliente):
    c, http, _ = cliente
    c.precos_todos()
    http.fora_do_ar = True
    r = c.precos_todos(forcar=True)
    assert r.desatualizado and r.aviso


def test_sem_cache_e_sem_api_gera_erro(cliente):
    c, http, _ = cliente
    http.fora_do_ar = True
    with pytest.raises(ErroUEX):
        c.terminais()


def test_tenta_endereco_alternativo(cliente):
    c, http, cfg = cliente
    cfg["api.uex_url"] = "https://endereco-velho.example/2.0"
    r = c.naves()
    assert r.dados and http.chamadas[0].startswith("https://endereco-velho")
    assert http.chamadas[-1].startswith("https://api.uexcorp.uk/2.0")


def test_distancias_simetricas_e_em_cache(cliente):
    c, http, _ = cliente
    d = c.distancias([(1, 2), (2, 1), (3, 5), (4, 4)])
    assert d[(1, 2)] == d[(2, 1)] == 3.0 and d[(5, 3)] == 8.0
    assert (4, 4) not in d
    n = len(http.chamadas)
    c.distancias([(2, 1), (5, 3)])
    assert len(http.chamadas) == n  # tudo veio do cache
