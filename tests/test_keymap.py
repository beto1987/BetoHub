"""Testes da conversão de atalhos (texto <-> códigos do Windows)."""

import pytest

from beto_hub.core import keymap


def test_interpreta_combinacao_comum():
    a = keymap.interpretar("Ctrl+Shift+F10")
    assert a.modificadores == keymap.MOD_CONTROL | keymap.MOD_SHIFT
    assert a.vk == 0x79  # VK_F10


def test_normaliza_ordem_e_maiusculas():
    assert keymap.normalizar("shift + ctrl + o") == "Ctrl+Shift+O"
    assert keymap.normalizar("alt+control+pgup") == "Ctrl+Alt+PageUp"


def test_tecla_sozinha_e_numpad():
    assert keymap.interpretar("F9").modificadores == 0
    assert keymap.interpretar("Ctrl+Num5").vk == 0x65
    assert keymap.interpretar("Alt+Num+").vk == 0x6B  # o "+" do teclado numérico


@pytest.mark.parametrize("texto", ["", "Ctrl+Shift", "Ctrl+A+B", "Ctrl+Ç", "Ctrl++"])
def test_rejeita_invalidos(texto):
    with pytest.raises(ValueError):
        keymap.interpretar(texto)


def test_ida_e_volta_de_todas_as_teclas():
    for nome, vk in keymap.TECLAS.items():
        texto = keymap.formatar(keymap.MOD_ALT, vk)
        assert keymap.interpretar(texto) == keymap.Atalho(keymap.MOD_ALT, vk), nome


def test_formatar_tecla_desconhecida():
    with pytest.raises(ValueError):
        keymap.formatar(0, 0xBA)  # tecla de pontuação (fora de propósito)
