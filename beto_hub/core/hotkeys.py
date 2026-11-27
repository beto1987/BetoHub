"""Atalhos globais por consulta ao estado do teclado (GetAsyncKeyState).

Histórico: a primeira versão usava RegisterHotKey, mas ela não funciona com o
Star Citizen em foco. Jogos que leem o teclado por Raw Input com a opção
RIDEV_NOHOTKEYS (ou que rodam como administrador) impedem que o Windows
entregue o atalho registrado.

Como funciona agora:
- A cada 25 ms o Hub pergunta ao Windows "estas teclas estão pressionadas?"
  (GetAsyncKeyState). É só leitura: não há gancho de teclado, não intercepta
  nem altera nada, não injeta código no jogo.
- O atalho dispara uma vez quando a combinação EXATA passa a estar pressionada
  (Ctrl+Shift+F10 não dispara com Ctrl+Alt+Shift+F10, e segurar não repete).
- A combinação NÃO é consumida: o jogo também recebe as teclas. Escolha uma
  que não faça nada no Star Citizen.
- O custo é desprezível (algumas chamadas por ciclo), e o timer só roda
  enquanto existe algum atalho ativo e não pausado.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

from beto_hub.core.i18n import tr
from . import keymap
from .logging_setup import obter_logger

log = obter_logger("atalhos")

EH_WINDOWS = sys.platform == "win32"
INTERVALO_MS = 25

# Virtual-Key dos modificadores (lados esquerdo/direito são tratados juntos)
VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
VK_LWIN, VK_RWIN = 0x5B, 0x5C

if EH_WINDOWS:
    import ctypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short

    def _pressionada(vk: int) -> bool:
        # Bit mais alto = tecla pressionada neste momento
        return bool(_user32.GetAsyncKeyState(vk) & 0x8000)
else:
    def _pressionada(vk: int) -> bool:  # fora do Windows: nunca dispara
        return False


def _modificadores_atuais() -> int:
    mods = 0
    if _pressionada(VK_CONTROL):
        mods |= keymap.MOD_CONTROL
    if _pressionada(VK_MENU):
        mods |= keymap.MOD_ALT
    if _pressionada(VK_SHIFT):
        mods |= keymap.MOD_SHIFT
    if _pressionada(VK_LWIN) or _pressionada(VK_RWIN):
        mods |= keymap.MOD_WIN
    return mods


@dataclass
class _Registro:
    atalho: keymap.Atalho
    ativo_antes: bool = False  # para disparar só na "borda" (ao apertar)


class GerenciadorAtalhos(QObject):
    """Registra atalhos por nome lógico (ex.: "overlay") e emite `acionado(nome)`."""

    acionado = Signal(str)

    def __init__(self):
        super().__init__()
        self._registros: dict[str, _Registro] = {}
        self._pausado = False
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVALO_MS)
        self._timer.timeout.connect(self._verificar)

    # ------------------------------------------------------------ API pública
    def registrar(self, nome: str, texto: str) -> tuple[bool, str]:
        """Ativa (ou troca) o atalho `nome`. Vale na hora. Devolve (ok, mensagem)."""
        self.remover(nome)
        try:
            atalho = keymap.interpretar(texto)
        except ValueError as erro:
            return False, str(erro)
        if not EH_WINDOWS:
            return False, tr("Atalhos globais só funcionam no Windows.")

        # Já pressionada no momento do registro? Espera soltar antes de disparar.
        self._registros[nome] = _Registro(atalho, ativo_antes=self._combinacao_ativa(atalho))
        self._atualizar_timer()
        log.info("Atalho '%s' ativo: %s", nome, atalho.texto)
        return True, tr("Atalho {atalho} ativo (funciona também com o jogo em foco).", atalho=atalho.texto)

    def remover(self, nome: str) -> None:
        if self._registros.pop(nome, None):
            log.info("Atalho '%s' removido", nome)
        self._atualizar_timer()

    def remover_todos(self) -> None:
        self._registros.clear()
        self._atualizar_timer()

    def pausar(self, pausado: bool) -> None:
        """Pausa os atalhos (ex.: enquanto a tela de Configurações está aberta)."""
        self._pausado = pausado
        if not pausado:
            # Ao retomar, ignora o que já estiver pressionado
            for reg in self._registros.values():
                reg.ativo_antes = self._combinacao_ativa(reg.atalho)
        self._atualizar_timer()

    def texto_ativo(self, nome: str) -> str | None:
        reg = self._registros.get(nome)
        return reg.atalho.texto if reg else None

    # ------------------------------------------------------------ interno
    def _atualizar_timer(self) -> None:
        deve_rodar = bool(self._registros) and not self._pausado
        if deve_rodar and not self._timer.isActive():
            self._timer.start()
        elif not deve_rodar and self._timer.isActive():
            self._timer.stop()

    @staticmethod
    def _combinacao_ativa(atalho: keymap.Atalho) -> bool:
        # Modificadores precisam bater EXATAMENTE (nem a mais, nem a menos)
        return _pressionada(atalho.vk) and _modificadores_atuais() == atalho.modificadores

    def _verificar(self) -> None:
        try:
            for nome, reg in list(self._registros.items()):
                ativo = self._combinacao_ativa(reg.atalho)
                if ativo and not reg.ativo_antes:
                    log.debug("Atalho acionado: %s", nome)
                    self.acionado.emit(nome)
                reg.ativo_antes = ativo
        except Exception:
            log.exception("Erro ao verificar atalhos; desativando a verificação")
            self._timer.stop()
