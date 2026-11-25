"""Simula a thread do scanner com tela e OCR falsos (sem Windows, sem winocr)."""

import time
from pathlib import Path

from PIL import Image

import plugins.mineracao.scanner as mod
from plugins.mineracao.logica.identificacao import carregar_assinaturas

DADOS = Path(__file__).resolve().parents[1] / "plugins" / "mineracao" / "data"


class CapturadorFalso:
    quadro = 0

    def capturar(self, regiao):
        CapturadorFalso.quadro += 1  # imagem sempre diferente: força a leitura
        return Image.new("RGB", (40, 12), (CapturadorFalso.quadro % 250, 0, 0))

    def fechar(self):
        pass


class MotorFalso:
    texto = "17,080"
    motor, idioma = "falso", "xx"

    def __init__(self, *a, **k):
        pass

    def ler(self, img):
        return MotorFalso.texto

    def ler_palavras(self, img):
        return "", []

    def fechar(self):
        pass


def test_fluxo_da_thread(monkeypatch):
    monkeypatch.setattr(mod, "Capturador", CapturadorFalso)
    monkeypatch.setattr(mod, "MotorOCR", MotorFalso)
    em_foco = {"valor": False}
    monkeypatch.setattr(mod, "jogo_em_primeiro_plano", lambda: em_foco["valor"])

    eventos = []
    opcoes = {"regiao_numero": {"left": 0, "top": 0, "width": 40, "height": 12},
              "intervalo_ms": 50, "so_com_jogo": True}
    t = mod.ThreadScanner(opcoes, carregar_assinaturas(DADOS / "signatures.json"),
                          lambda tipo, dados: eventos.append((tipo, dados)))
    t.start()
    try:
        time.sleep(0.6)
        assert ("status", ("Scanner pausado", "ajuda")) in eventos
        t.ativo = True
        time.sleep(0.6)
        assert any(e == ("status", ("Aguardando o Star Citizen em primeiro plano", "ajuda")) for e in eventos)
        assert not any(tipo == "resultado" for tipo, _ in eventos)

        em_foco["valor"] = True
        time.sleep(0.8)
        resultados = [d for tipo, d in eventos if tipo == "resultado"]
        assert len(resultados) == 1  # confirmado (lido 2x) e mostrado uma vez só
        valor, candidatos = resultados[0][0]
        assert valor == 17080 and candidatos[0]["sig"]["name"] == "Iron" and candidatos[0]["count"] == 4
    finally:
        t.parar()
        t.join(2)
    assert not t.is_alive()
