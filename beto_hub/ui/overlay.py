"""Overlay: janela única, sempre visível, translúcida, com uma aba por módulo.

- Não rouba o foco do jogo ao aparecer (WindowDoesNotAcceptFocus).
- Não aparece na barra de tarefas (Qt.Tool).
- "Clique atravessa": os cliques passam direto para o jogo. Nesse modo não
  dá para clicar no overlay; desligue pelo atalho, pela bandeja ou pelo menu.
- Funciona com o jogo em "Janela sem bordas". Em tela cheia exclusiva o
  Windows não desenha outras janelas por cima.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizeGrip, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from beto_hub.core.i18n import tr
from ..core.config import GerenciadorConfig
from ..core.logging_setup import obter_logger
from .widgets import PainelEmConstrucao

log = obter_logger("overlay")

OPACIDADE_MIN, OPACIDADE_MAX = 0.20, 1.00


class _BarraTitulo(QFrame):
    """Barra superior que permite arrastar o overlay."""

    def __init__(self, overlay: "JanelaOverlay"):
        super().__init__(overlay)
        self.setObjectName("OverlayBarra")
        self._overlay = overlay
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 2, 2)
        titulo = QLabel("◈ STARHUB")
        titulo.setObjectName("OverlayTitulo")
        layout.addWidget(titulo)
        layout.addStretch(1)
        # Aviso de modo: aparece quando os cliques estão atravessando para o jogo
        self.aviso_clique = QLabel("⇣ " + tr("CLIQUE ATRAVESSA"))
        self.aviso_clique.setObjectName("OverlayAvisoClique")
        self.aviso_clique.setToolTip(tr("Os cliques estão indo para o jogo. Use o atalho para voltar."))
        self.aviso_clique.hide()
        layout.addWidget(self.aviso_clique)
        fechar = QToolButton()
        fechar.setObjectName("BotaoBarra")
        fechar.setText("✕")
        fechar.setToolTip(tr("Esconder overlay"))
        fechar.clicked.connect(overlay.hide)
        layout.addWidget(fechar)

    def mousePressEvent(self, evento):  # noqa: N802
        if evento.button() == Qt.LeftButton and self._overlay.windowHandle():
            # Arrasto nativo do Windows: suave e respeita vários monitores.
            self._overlay.windowHandle().startSystemMove()
        super().mousePressEvent(evento)


class JanelaOverlay(QWidget):
    visibilidadeAlterada = Signal(bool)

    def __init__(self, config: GerenciadorConfig):
        super().__init__(None)
        self.config = config
        self._ids_abas: list[str] = []
        self.setWindowTitle("StarHub — Overlay")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMinimumSize(260, 180)

        moldura = QFrame(self)
        moldura.setObjectName("OverlayMoldura")
        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        externo.addWidget(moldura)

        layout = QVBoxLayout(moldura)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self._barra = _BarraTitulo(self)
        layout.addWidget(self._barra)

        self.abas = QTabWidget()
        self.abas.setObjectName("OverlayAbas")
        self.abas.setDocumentMode(True)
        self.abas.currentChanged.connect(self._ao_trocar_aba)
        layout.addWidget(self.abas, 1)

        rodape = QHBoxLayout()
        rodape.setContentsMargins(0, 0, 0, 0)
        rodape.addStretch(1)
        rodape.addWidget(QSizeGrip(moldura), 0, Qt.AlignBottom | Qt.AlignRight)
        layout.addLayout(rodape)

        # Salva posição/tamanho só depois que o usuário parar de mexer.
        self._timer_salvar = QTimer(self, singleShot=True, interval=700)
        self._timer_salvar.timeout.connect(self._salvar_geometria)

        self._restaurar_geometria()
        self.aplicar_config()

    # ------------------------------------------------------------ painéis
    def adicionar_painel(self, id_modulo: str, nome: str, widget: QWidget) -> None:
        self.abas.addTab(widget, nome.upper())
        self._ids_abas.append(id_modulo)

    def finalizar_paineis(self) -> None:
        """Chamado depois de todos os plugins: placeholder + restaura a última aba."""
        if self.abas.count() == 0:
            self.adicionar_painel("", "Hub", PainelEmConstrucao(
                "Overlay", tr("Nenhum módulo tem painel de overlay ainda."), compacto=True
            ))
        ultima = self.config.obter("overlay.aba", "")
        if ultima in self._ids_abas:
            self.abas.setCurrentIndex(self._ids_abas.index(ultima))

    def _ao_trocar_aba(self, indice: int) -> None:
        if 0 <= indice < len(self._ids_abas) and self._ids_abas[indice]:
            self.config.atualizar({"overlay.aba": self._ids_abas[indice]}, silencioso=True)

    # ------------------------------------------------------------ config
    def aplicar_config(self) -> None:
        """Aplica opacidade e clique-atravessa a partir do config (vale na hora)."""
        self.definir_opacidade(float(self.config.obter("overlay.opacidade", 0.85)))
        self.definir_clique_atravessa(bool(self.config.obter("overlay.clique_atravessa", False)))

    def definir_opacidade(self, valor: float) -> None:
        self.setWindowOpacity(max(OPACIDADE_MIN, min(OPACIDADE_MAX, valor)))

    def definir_clique_atravessa(self, ativo: bool) -> None:
        self._barra.aviso_clique.setVisible(ativo)
        if bool(self.windowFlags() & Qt.WindowTransparentForInput) == ativo:
            return
        visivel = self.isVisible()
        # Trocar flags recria a janela nativa; precisa mostrar de novo.
        self.setWindowFlag(Qt.WindowTransparentForInput, ativo)
        if visivel:
            self.show()
        log.info("Clique atravessa: %s", "ligado" if ativo else "desligado")

    @property
    def clique_atravessa(self) -> bool:
        return bool(self.windowFlags() & Qt.WindowTransparentForInput)

    # ------------------------------------------------------------ mostrar/esconder
    def alternar(self) -> None:
        self.setVisible(not self.isVisible())

    def showEvent(self, evento):  # noqa: N802
        super().showEvent(evento)
        self.visibilidadeAlterada.emit(True)

    def hideEvent(self, evento):  # noqa: N802
        super().hideEvent(evento)
        self.visibilidadeAlterada.emit(False)

    # ------------------------------------------------------------ geometria
    def _restaurar_geometria(self) -> None:
        c = self.config
        self.resize(int(c.obter("overlay.largura", 420)), int(c.obter("overlay.altura", 560)))
        x, y = int(c.obter("overlay.x", 40)), int(c.obter("overlay.y", 40))
        # Se o monitor onde estava sumiu, volta para o canto do monitor principal.
        if not any(t.availableGeometry().contains(x + 20, y + 20) for t in QGuiApplication.screens()):
            x, y = 40, 40
        self.move(x, y)

    def moveEvent(self, evento):  # noqa: N802
        super().moveEvent(evento)
        self._timer_salvar.start()

    def resizeEvent(self, evento):  # noqa: N802
        super().resizeEvent(evento)
        self._timer_salvar.start()

    def _salvar_geometria(self) -> None:
        g = self.geometry()
        self.config.atualizar(
            {"overlay.x": g.x(), "overlay.y": g.y(), "overlay.largura": g.width(), "overlay.altura": g.height()},
            silencioso=True,
        )
