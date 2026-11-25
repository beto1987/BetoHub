"""Testes da lógica da Mineração (sem tela, sem OCR real)."""

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from beto_hub.services.ocr.preprocess import preprocessar, variacoes
from plugins.mineracao.logica.identificacao import carregar_assinaturas, extrair_numeros, identificar
from plugins.mineracao.logica.importacao import converter_config, importar
from plugins.mineracao.logica.quebra import DadosMineracao, ler_painel_por_posicao, ler_painel_por_texto
from plugins.mineracao.logica.refino import TabelaRefino, chave_minerio

DADOS = Path(__file__).resolve().parents[1] / "plugins" / "mineracao" / "data"


@pytest.fixture(scope="module")
def assinaturas():
    return carregar_assinaturas(DADOS / "signatures.json")


@pytest.fixture(scope="module")
def dados():
    return DadosMineracao(DADOS / "mining_data.json")


def test_identifica_multiplos_da_assinatura(assinaturas):
    iron = next(s for s in assinaturas if s["name"] == "Iron")
    c = identificar(iron["base"] * 4, assinaturas)
    assert any(x["sig"]["name"] == "Iron" and x["count"] == 4 and x["exact"] for x in c)


def test_identificacao_aproximada_quando_ocr_erra_um_digito(assinaturas):
    quant = next(s for s in assinaturas if s["name"] == "Quantainium")
    c = identificar(quant["base"] * 2 + 3, assinaturas)
    assert c and not c[0]["exact"]


def test_extrai_numeros_e_corrige_letras():
    assert extrair_numeros("IS,ooo 12.680 lixo 99", 1500, 200000) == [(15000, False), (12680, True)]
    assert extrair_numeros("abc", 1500, 200000) == []


def test_quebra_e_gadget(dados):
    lo = dados.normalizar({"ship": "Prospector", "lasers": [{"head": "Arbor MH1", "modules": []}]})
    facil = dados.analisar(lo, 2000, 10)
    assert facil["base"]["breaks"] and facil["base"]["throttle"] < 100
    dificil = dados.analisar(lo, 90000, 85)
    assert not dificil["base"]["breaks"]


def test_normalizar_loadout_invalido(dados):
    assert dados.normalizar(None)["ship"] in dados.naves
    mole = dados.normalizar({"ship": "MOLE", "lasers": []})
    assert len(mole["lasers"]) == dados.naves["MOLE"]["lasers"]


def test_painel_da_rocha():
    palavras = [("MASS", 10, 10, 40, 12), ("15", 60, 10, 15, 12), ("824", 78, 10, 20, 12),
                ("RESISTANCE", 10, 30, 80, 12), ("23%", 95, 30, 25, 12), ("EASY", 10, 50, 30, 12)]
    assert ler_painel_por_posicao(palavras) == {"mass": 15824.0, "resistance": 23.0, "difficulty": "EASY"}
    assert ler_painel_por_texto("MASS 8.540 RES 40%")["resistance"] == 40.0


def test_refino_uex_ignora_sufixos_e_bonus_negativo():
    linhas = [
        {"commodity_name": "Quantainium (Raw)", "terminal_name": "ARC-L1", "star_system_name": "Stanton", "value": 6},
        {"commodity_name": "Quantainium (Raw)", "terminal_name": "CRU-L1", "star_system_name": "Stanton", "value": -3},
        {"commodity_name": "Quantainium (Raw)", "terminal_name": "Levski", "star_system_name": "Nyx", "value": 9},
        {"commodity_name": "Iron (Ore)", "terminal_name": "MIC-L1", "star_system_name": "Stanton", "value": "x"},
    ]
    t = TabelaRefino.de_uex(linhas)
    melhores = t.melhores("Quantainium")
    assert [r.nome for r in melhores] == ["Levski", "ARC-L1"]
    assert melhores[0].rotulo == "Levski (Nyx) +9%"
    assert t.melhores("Gold") is None
    assert chave_minerio("Quantaínium (ORE)") == "quantainium"


def test_refino_arquivo_reserva():
    t = TabelaRefino.de_arquivo(DADOS / "refineries_reserva.json")
    assert t.fonte == "arquivo" and len(t) > 5


def test_importacao_do_scanner_antigo(tmp_path):
    antiga = tmp_path / "SCScanner"
    antiga.mkdir()
    (antiga / "config.json").write_text(json.dumps({
        "region": {"left": 1, "top": 2, "width": 30, "height": 40}, "threshold": 150,
        "rock_region": None, "mining": {"ship": "MOLE", "lasers": []}, "overlay_x": 9,
    }), encoding="utf-8")
    (antiga / "history.json").write_text(json.dumps([{"time": "10:00:00", "results": [[3170, []]]}]),
                                         encoding="utf-8")
    opcoes, historico, origem = importar([antiga])
    assert opcoes == {"regiao_numero": {"left": 1, "top": 2, "width": 30, "height": 40},
                      "limiar": 150, "loadout": {"ship": "MOLE", "lasers": []}}
    assert len(historico) == 1 and origem == str(antiga)
    assert importar([tmp_path / "nao_existe"]) == ({}, [], "")
    assert converter_config({"scale": 4, "x": 1}) == {"escala": 4}


def test_preprocessamento_gera_imagem_preto_e_branco():
    img = Image.new("RGB", (60, 20), (10, 10, 30))
    ImageDraw.Draw(img).text((5, 4), "3170", fill=(240, 200, 80))
    out = preprocessar(img, {"escala": 3, "limiar": 140})
    assert out.size == (60 * 3 + 40, 20 * 3 + 40)
    hist = out.histogram()
    assert all(n == 0 for i, n in enumerate(hist) if i not in (0, 255))  # só preto e branco
    assert variacoes({"limiar": 140})[0] == ("lum", 140)
    assert len(variacoes({"limiar": 140})) == 7
