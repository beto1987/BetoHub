"""Seleção de área da tela: print congelado, escurecido, e um retângulo arrastado.

- Uma janela por monitor, com o print daquele monitor (QScreen.grabWindow).
- As janelas do Hub (principal e overlay) somem durante a seleção para não
  cobrir o HUD do jogo, e voltam no final.
- A área é salva em pixels FÍSICOS: no Windows usamos a posição real do
  cursor (GetCursorPos), que é a mesma referência da captura (mss).
- Esc cancela. Sem seleção em 60 s, cancela sozinho.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    def _cursor_fisico() -> tuple[int, int] | None:
        p = wintypes.POINT()
        return (p.x, p.y) if ctypes.windll.user32.GetCursorPos(ctypes.byref(p)) else None
else:
    def _cursor_fisico() -> tuple[int, int] | None:
        return None


class _TelaSelecao(QWidget):
    def __init__(self, seletor: "SeletorArea", tela, texto: str):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.seletor, self.tela, self.texto = seletor, tela, texto
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(tela.geometry())
        self.original: QPixmap = tela.grabWindow(0)
        self.escuro = QPixmap(self.original)
        p = QPainter(self.escuro)
        p.fillRect(self.escuro.rect(), QColor(0, 0, 0, 115))
        p.end()
        self._inicio: QPoint | None = None
        self._fim: QPoint | None = None
        self._inicio_fisico: tuple[int, int] | None = None

    def paintEvent(self, _evento):  # noqa: N802
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.escuro)
        if self._inicio and self._fim:
            r = QRect(self._inicio, self._fim).normalized()
            dpr = self.original.devicePixelRatio()
            origem = QRect(int(r.x() * dpr), int(r.y() * dpr), int(r.width() * dpr), int(r.height() * dpr))
            p.drawPixmap(r, self.original, origem)  # área selecionada em brilho normal
            p.setPen(QPen(QColor("#00ff88"), 2))
            p.drawRect(r)
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", 15, QFont.Bold))
        p.drawText(self.rect().adjusted(0, 24, 0, 0), Qt.AlignHCenter | Qt.AlignTop, self.texto)
        p.end()

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._inicio = self._fim = e.position().toPoint()
            self._inicio_fisico = _cursor_fisico()
            self.update()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._inicio:
            self._fim = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() != Qt.LeftButton or not self._inicio:
            return
        self._fim = e.position().toPoint()
        r = QRect(self._inicio, self._fim).normalized()
        if r.width() < 8 or r.height() < 8:
            self._inicio = self._fim = None
            self.update()
            return
        fim_fisico = _cursor_fisico()
        if self._inicio_fisico and fim_fisico:
            (x0, y0), (x1, y1) = self._inicio_fisico, fim_fisico
            regiao = {"left": min(x0, x1), "top": min(y0, y1), "width": abs(x1 - x0), "height": abs(y1 - y0)}
        else:  # fora do Windows: converte pela escala da tela
            dpr = self.tela.devicePixelRatio()
            g = self.tela.geometry()
            regiao = {"left": int((g.x() + r.x()) * dpr), "top": int((g.y() + r.y()) * dpr),
                      "width": int(r.width() * dpr), "height": int(r.height() * dpr)}
        self.seletor._concluir(regiao)

    def keyPressEvent(self, e):  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self.seletor._concluir(None)


class SeletorArea(QObject):
    """Uso: seletor.concluido.connect(cb); seletor.iniciar("texto", atraso_s=5)"""

    concluido = Signal(object)  # dict da região (pixels físicos) ou None se cancelado
    contagem = Signal(int)      # segundos restantes antes do print

    def __init__(self, parent=None):
        super().__init__(parent)
        self._telas: list[_TelaSelecao] = []
        self._escondidas: list[QWidget] = []
        self._ativo = False
        self._restante = 0
        self._relogio = QTimer(self, interval=1000)
        self._relogio.timeout.connect(self._tique)
        self._limite = QTimer(self, singleShot=True, interval=60_000)
        self._limite.timeout.connect(lambda: self._concluir(None))

    @property
    def ativo(self) -> bool:
        return self._ativo

    def iniciar(self, texto: str, atraso_s: int = 0) -> None:
        if self._ativo:
            return
        self._ativo = True
        self._texto = texto
        # Esconde as janelas do Hub para não aparecerem no print
        self._escondidas = [w for w in QApplication.topLevelWidgets() if w.isVisible()]
        for w in self._escondidas:
            w.hide()
        if atraso_s > 0:
            self._restante = atraso_s
            self.contagem.emit(self._restante)
            self._relogio.start()
        else:
            QTimer.singleShot(300, self._abrir)  # tempo para as janelas sumirem da tela

    def _tique(self) -> None:
        self._restante -= 1
        self.contagem.emit(self._restante)
        if self._restante <= 0:
            self._relogio.stop()
            self._abrir()

    def _abrir(self) -> None:
        self._telas = [_TelaSelecao(self, tela, self._texto) for tela in QGuiApplication.screens()]
        for t in self._telas:
            t.show()
            t.raise_()
        if self._telas:
            self._telas[0].activateWindow()
            self._telas[0].setFocus()
        self._limite.start()

    def _concluir(self, regiao) -> None:
        if not self._ativo:
            return
        self._ativo = False
        self._relogio.stop()
        self._limite.stop()
        for t in self._telas:
            t.close()
        self._telas = []
        for w in self._escondidas:
            w.show()
        self._escondidas = []
        self.concluido.emit(regiao)
