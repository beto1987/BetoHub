"""Campo que captura a combinação de teclas pressionada pelo usuário.

Como usar: clique no campo e pressione a combinação (ex.: Ctrl+Shift+F10).
- Esc cancela e volta ao valor anterior.
- Backspace/Delete sozinhos limpam o campo.
O texto gerado segue o formato do config.toml (keymap.formatar).
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit

from beto_hub.core.i18n import tr
from ...core import keymap
from ..theme import repolir


def _i(valor) -> int:
    """Enums do PySide6 -> int (funciona tanto com IntEnum quanto com Enum)."""
    return int(getattr(valor, "value", valor))


_TECLAS_MODIFICADORAS = {_i(k) for k in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr)}

# Usado só fora do Windows (desenvolvimento): Qt.Key -> VK.
_QT_PARA_VK: dict[int, int] = {
    _i(getattr(Qt, f"Key_F{n}")): 0x6F + n for n in range(1, 25)
}
_QT_PARA_VK.update({_i(k): v for k, v in (
    (Qt.Key_Space, 0x20), (Qt.Key_Tab, 0x09), (Qt.Key_Return, 0x0D), (Qt.Key_Enter, 0x0D),
    (Qt.Key_Pause, 0x13), (Qt.Key_PageUp, 0x21), (Qt.Key_PageDown, 0x22), (Qt.Key_End, 0x23),
    (Qt.Key_Home, 0x24), (Qt.Key_Left, 0x25), (Qt.Key_Up, 0x26), (Qt.Key_Right, 0x27),
    (Qt.Key_Down, 0x28), (Qt.Key_Insert, 0x2D), (Qt.Key_Delete, 0x2E), (Qt.Key_ScrollLock, 0x91),
)})


def _vk_do_evento(evento: QKeyEvent) -> int:
    """Código Virtual-Key da tecla. No Windows o Qt já informa o código nativo."""
    if sys.platform == "win32" and evento.nativeVirtualKey():
        return int(evento.nativeVirtualKey())
    tecla = _i(evento.key())
    eh_numero = _i(Qt.Key_0) <= tecla <= _i(Qt.Key_9)
    if eh_numero and evento.modifiers() & Qt.KeypadModifier:
        return 0x60 + (tecla - _i(Qt.Key_0))
    if eh_numero or _i(Qt.Key_A) <= tecla <= _i(Qt.Key_Z):
        return tecla  # letras e números: código Qt == VK
    return _QT_PARA_VK.get(tecla, 0)


class CampoAtalho(QLineEdit):
    atalhoAlterado = Signal(str)  # texto novo ("" = sem atalho)

    def __init__(self, texto: str = "", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)  # o texto só muda pela captura
        self.setPlaceholderText(tr("Clique aqui e pressione a combinação"))
        self.setToolTip(tr("Clique e pressione a combinação.\nEsc cancela · Backspace limpa"))
        self._valor = texto
        self._capturando = False
        self.setText(texto)

    # ------------------------------------------------------------ API
    def valor(self) -> str:
        return self._valor

    def definir_valor(self, texto: str) -> None:
        self._valor = texto
        self.setText(texto)

    # ------------------------------------------------------------ captura
    def _modo_captura(self, ativo: bool) -> None:
        self._capturando = ativo
        self.setProperty("capturando", "true" if ativo else "false")
        repolir(self)
        self.setText(tr("Pressione a combinação…") if ativo else self._valor)

    def focusInEvent(self, evento):  # noqa: N802
        super().focusInEvent(evento)
        self._modo_captura(True)

    def focusOutEvent(self, evento):  # noqa: N802
        super().focusOutEvent(evento)
        self._modo_captura(False)

    def focusNextPrevChild(self, proximo: bool) -> bool:  # noqa: N802
        # Durante a captura, Tab é uma tecla como as outras.
        return False if self._capturando else super().focusNextPrevChild(proximo)

    def keyPressEvent(self, evento: QKeyEvent) -> None:  # noqa: N802
        if not self._capturando:
            return super().keyPressEvent(evento)
        tecla = _i(evento.key())
        mods_qt = evento.modifiers()
        sem_mods = not (mods_qt & (Qt.ControlModifier | Qt.AltModifier | Qt.ShiftModifier | Qt.MetaModifier))

        if tecla == _i(Qt.Key_Escape) and sem_mods:
            self.clearFocus()  # sai da captura mantendo o valor anterior
            return
        if tecla in (_i(Qt.Key_Backspace), _i(Qt.Key_Delete)) and sem_mods:
            self._confirmar("")
            return

        mods = 0
        if mods_qt & Qt.ControlModifier:
            mods |= keymap.MOD_CONTROL
        if mods_qt & Qt.AltModifier:
            mods |= keymap.MOD_ALT
        if mods_qt & Qt.ShiftModifier:
            mods |= keymap.MOD_SHIFT
        if mods_qt & Qt.MetaModifier:
            mods |= keymap.MOD_WIN

        if tecla in _TECLAS_MODIFICADORAS:
            # Mostra o que já está pressionado enquanto espera a tecla principal
            parcial = [n for b, n in ((keymap.MOD_CONTROL, "Ctrl"), (keymap.MOD_ALT, "Alt"),
                                      (keymap.MOD_SHIFT, "Shift"), (keymap.MOD_WIN, "Win")) if mods & b]
            self.setText("+".join(parcial) + "+…" if parcial else tr("Pressione a combinação…"))
            return

        vk = _vk_do_evento(evento)
        try:
            texto = keymap.formatar(mods, vk)
        except ValueError:
            self.setText(tr("Tecla não suportada — tente outra"))
            return
        self._confirmar(texto)

    def keyReleaseEvent(self, evento: QKeyEvent) -> None:  # noqa: N802
        evento.accept()  # não deixa o diálogo reagir (ex.: Enter = OK)

    def _confirmar(self, texto: str) -> None:
        self._valor = texto
        self.clearFocus()  # encerra a captura e mostra o valor
        self.setText(texto)
        self.atalhoAlterado.emit(texto)
