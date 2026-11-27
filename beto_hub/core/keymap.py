"""Conversão entre texto de atalho ("Ctrl+Shift+F10") e códigos do Windows.

Módulo puro (sem Qt), para poder ser testado em qualquer máquina.

Formato salvo no config: modificadores na ordem Ctrl+Alt+Shift+Win, depois
UMA tecla. Teclas de pontuação (; , . [ etc.) ficam de fora de propósito:
no teclado ABNT2 elas mudam de lugar e o atalho ficaria imprevisível.
"""

from __future__ import annotations

from dataclasses import dataclass

from beto_hub.core.i18n import tr

# Modificadores do RegisterHotKey (WinUser.h)
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000  # segurar a tecla não dispara várias vezes

_ORDEM_MODS = ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"))
_APELIDOS_MODS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "ctl": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "windows": MOD_WIN, "meta": MOD_WIN, "super": MOD_WIN,
}


def _montar_tabela() -> dict[str, int]:
    """Nome da tecla -> Virtual-Key code do Windows."""
    t: dict[str, int] = {}
    for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        t[c] = ord(c)  # letras e números: VK == código ASCII
    for n in range(1, 25):
        t[f"F{n}"] = 0x6F + n  # VK_F1 = 0x70
    for n in range(10):
        t[f"Num{n}"] = 0x60 + n  # VK_NUMPAD0 = 0x60
    t.update({
        "Num*": 0x6A, "Num+": 0x6B, "Num-": 0x6D, "Num.": 0x6E, "Num/": 0x6F,
        "Space": 0x20, "Tab": 0x09, "Enter": 0x0D, "Pause": 0x13,
        "PageUp": 0x21, "PageDown": 0x22, "End": 0x23, "Home": 0x24,
        "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28,
        "Insert": 0x2D, "Delete": 0x2E, "ScrollLock": 0x91,
    })
    return t


TECLAS: dict[str, int] = _montar_tabela()
_NOME_POR_VK: dict[int, str] = {vk: nome for nome, vk in TECLAS.items()}
_NOME_POR_MINUSCULO: dict[str, str] = {nome.lower(): nome for nome in TECLAS}
# Alguns apelidos comuns em português/inglês
_NOME_POR_MINUSCULO.update({
    "espaço": "Space", "espaco": "Space", "del": "Delete", "ins": "Insert",
    "pgup": "PageUp", "pgdn": "PageDown", "pgdown": "PageDown",
    "esquerda": "Left", "direita": "Right", "cima": "Up", "baixo": "Down",
})


@dataclass(frozen=True)
class Atalho:
    modificadores: int  # combinação de MOD_*
    vk: int             # Virtual-Key code

    @property
    def texto(self) -> str:
        return formatar(self.modificadores, self.vk)


def nome_tecla(vk: int) -> str | None:
    return _NOME_POR_VK.get(vk)


def formatar(modificadores: int, vk: int) -> str:
    partes = [nome for bit, nome in _ORDEM_MODS if modificadores & bit]
    nome = nome_tecla(vk)
    if nome is None:
        raise ValueError(tr("Tecla não suportada (código {codigo}).", codigo=f"{vk:#04x}"))
    partes.append(nome)
    return "+".join(partes)


def interpretar(texto: str) -> Atalho:
    """Converte "ctrl + shift + f10" em Atalho. Lança ValueError com mensagem amigável."""
    if not texto or not texto.strip():
        raise ValueError(tr("Atalho vazio."))
    # Trata "Num+" (o + faz parte do nome da tecla)
    bruto = texto.replace(" ", "")
    tokens: list[str] = []
    for parte in bruto.split("+"):
        if parte == "" and tokens and tokens[-1].lower() == "num":
            tokens[-1] = "Num+"
        elif parte:
            tokens.append(parte)
        else:
            raise ValueError(tr("Atalho mal formado: '{texto}'.", texto=texto))

    mods = 0
    tecla: str | None = None
    for token in tokens:
        baixo = token.lower()
        if baixo in _APELIDOS_MODS:
            mods |= _APELIDOS_MODS[baixo]
        elif baixo in _NOME_POR_MINUSCULO:
            if tecla is not None:
                raise ValueError(tr("Use só uma tecla principal (além de Ctrl/Alt/Shift/Win)."))
            tecla = _NOME_POR_MINUSCULO[baixo]
        else:
            raise ValueError(tr("Tecla desconhecida: '{tecla}'.", tecla=token))
    if tecla is None:
        raise ValueError(tr("Falta a tecla principal (ex.: F10, O, Num5)."))
    return Atalho(mods, TECLAS[tecla])


def normalizar(texto: str) -> str:
    """Devolve o texto no formato padrão. Ex.: "shift+ctrl+o" -> "Ctrl+Shift+O"."""
    return interpretar(texto).texto
