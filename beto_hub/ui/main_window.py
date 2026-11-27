"""Janela principal: cabeçalho, uma aba por módulo e barra de status."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QTabWidget,
    QVBoxLayout, QWidget,
)

from beto_hub.core.i18n import tr
from .. import NOME_APP, __version__
from ..core import paths
from ..core.logging_setup import obter_logger
from ..core.plugin_loader import ERRO, OK
from .widgets import PainelEmConstrucao, PainelErroPlugin

if TYPE_CHECKING:
    from ..app import HubApp

log = obter_logger("janela")


class JanelaPrincipal(QMainWindow):
    def __init__(self, hub: "HubApp"):
        super().__init__()
        self.hub = hub
        self.setWindowTitle(NOME_APP)
        self.setMinimumSize(900, 560)

        central = QWidget()
        central.setObjectName("Fundo")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._criar_cabecalho())

        self.abas = QTabWidget()
        self.abas.setDocumentMode(False)
        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(10, 10, 10, 6)
        conteudo.addWidget(self.abas)
        layout.addLayout(conteudo, 1)
        self.setCentralWidget(central)

        self._criar_menus()
        self._criar_status()
        self._montar_abas()
        self._restaurar_geometria()

    # ------------------------------------------------------------ montagem
    def _criar_cabecalho(self) -> QFrame:
        cab = QFrame()
        cab.setObjectName("Cabecalho")
        cab.setFixedHeight(70)
        linha = QHBoxLayout(cab)
        linha.setContentsMargins(18, 8, 14, 8)

        textos = QVBoxLayout()
        textos.setSpacing(0)
        sub = QLabel("STAR CITIZEN")
        sub.setObjectName("CabecalhoSubtitulo")
        titulo = QLabel("BETO HUB")
        titulo.setObjectName("CabecalhoTitulo")
        textos.addWidget(sub)
        textos.addWidget(titulo)
        linha.addLayout(textos)

        versao = QLabel(f"v{__version__}")
        versao.setObjectName("CabecalhoVersao")
        linha.addWidget(versao, 0, Qt.AlignBottom)
        linha.addStretch(1)

        self.botao_overlay = QPushButton(tr("OVERLAY"))
        self.botao_overlay.setCheckable(True)
        self.botao_overlay.setToolTip(tr("Mostrar/esconder o overlay"))
        self.botao_overlay.clicked.connect(self.hub.alternar_overlay)
        botao_config = QPushButton(tr("CONFIGURAÇÕES"))
        botao_config.clicked.connect(self.hub.abrir_configuracoes)
        linha.addWidget(self.botao_overlay)
        linha.addWidget(botao_config)
        return cab

    def _criar_menus(self) -> None:
        barra = self.menuBar()

        arquivo = barra.addMenu(tr("&Arquivo"))
        self._acao(arquivo, tr("Configurações…"), self.hub.abrir_configuracoes, QKeySequence("Ctrl+,"))
        arquivo.addSeparator()
        self._acao(arquivo, tr("Abrir arquivo de configuração"), lambda: self._abrir(paths.arquivo_config()))
        self._acao(arquivo, tr("Abrir pasta de dados"), lambda: self._abrir(paths.pasta_dados()))
        self._acao(arquivo, tr("Abrir pasta de logs"), lambda: self._abrir(paths.pasta_logs()))
        arquivo.addSeparator()
        self._acao(arquivo, tr("Sair"), self.hub.sair, QKeySequence("Ctrl+Q"))

        exibir = barra.addMenu(tr("&Exibir"))
        self._acao(exibir, tr("Mostrar/esconder overlay"), self.hub.alternar_overlay)
        self.acao_clique = self._acao(exibir, tr("Overlay: clique atravessa"), self.hub.alternar_clique_atravessa)
        self.acao_clique.setCheckable(True)

        ajuda = barra.addMenu(tr("A&juda"))
        self._acao(ajuda, tr("Sobre"), self._sobre)

    def _acao(self, menu, texto, funcao, atalho: QKeySequence | None = None) -> QAction:
        acao = QAction(texto, self)
        if atalho:
            acao.setShortcut(atalho)  # atalho LOCAL (só com a janela em foco)
        acao.triggered.connect(lambda *_: funcao())
        menu.addAction(acao)
        return acao

    def _criar_status(self) -> None:
        status = self.statusBar()
        self.rotulo_overlay = QLabel()
        self.rotulo_atalho = QLabel()
        status.addPermanentWidget(self.rotulo_atalho)
        status.addPermanentWidget(self.rotulo_overlay)

    def selecionar_aba(self, id_modulo: str) -> None:
        if id_modulo in self._indice_por_id:
            self.abas.setCurrentIndex(self._indice_por_id[id_modulo])

    def _montar_abas(self) -> None:
        self._indice_por_id: dict[str, int] = {}
        carregados = [p for p in self.hub.plugins if p.estado in (OK, ERRO)]
        if not carregados:
            self.abas.addTab(PainelEmConstrucao(
                tr("Nenhum módulo"), tr("Nenhum módulo ativo foi encontrado na pasta plugins."),
            ), "HUB")
            return
        for plugin in carregados:
            indice = self.abas.addTab(self._criar_conteudo(plugin), tr(plugin.nome).upper())
            self._indice_por_id[plugin.id] = indice

    def _criar_conteudo(self, plugin) -> QWidget:
        if plugin.estado == OK:
            try:
                return plugin.instancia.criar_aba(self.abas)
            except Exception as erro:
                log.exception("Erro ao criar a aba do módulo %s", plugin.id)
                import traceback
                return PainelErroPlugin(tr(plugin.nome), f"{type(erro).__name__}: {erro}",
                                        traceback.format_exc(), str(paths.pasta_logs()))
        return PainelErroPlugin(tr(plugin.nome), plugin.erro, plugin.detalhe, str(paths.pasta_logs()))

    # ------------------------------------------------------------ estado
    def atualizar_status(self, overlay_visivel: bool, clique_atravessa: bool,
                         atalho_overlay: str | None, atalho_clique: str | None) -> None:
        self.botao_overlay.setChecked(overlay_visivel)
        self.acao_clique.setChecked(clique_atravessa)
        estado = tr("visível") if overlay_visivel else tr("oculto")
        if clique_atravessa:
            estado += " · " + tr("clique atravessa")
        self.rotulo_overlay.setText(tr("Overlay: {estado}", estado=estado))
        self.rotulo_atalho.setText(tr(
            "Atalhos — overlay: {overlay} · clique: {clique}",
            overlay=atalho_overlay or tr("desativado"), clique=atalho_clique or tr("desativado")))

    def mensagem(self, texto: str, ms: int = 5000) -> None:
        self.statusBar().showMessage(texto, ms)

    # ------------------------------------------------------------ utilidades
    @staticmethod
    def _abrir(caminho) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(caminho)))

    def _sobre(self) -> None:
        QMessageBox.about(
            self, tr("Sobre o {app}", app=NOME_APP),
            f"<b>{NOME_APP}</b> v{__version__}<br><br>"
            + tr("App de apoio ao Star Citizen.") + "<br>"
            + tr("Só lê a tela, o Game.log e APIs da comunidade (UEX Corp, Star Citizen Wiki). "
                 "Não modifica arquivos do jogo nem injeta código.") + "<br><br>"
            + tr("Star Citizen é marca da Cloud Imperium Games. Projeto de fã, sem vínculo oficial."),
        )

    # ------------------------------------------------------------ geometria
    def _restaurar_geometria(self) -> None:
        c = self.hub.config
        self.resize(int(c.obter("janela.largura", 1200)), int(c.obter("janela.altura", 760)))
        x, y = int(c.obter("janela.x", -1)), int(c.obter("janela.y", -1))
        tela = QGuiApplication.primaryScreen().availableGeometry()
        visivel = any(t.availableGeometry().contains(x + 50, y + 50) for t in QGuiApplication.screens())
        if x < 0 or y < 0 or not visivel:
            self.move(tela.center() - self.rect().center())
        else:
            self.move(x, y)
        self._iniciar_maximizada = bool(c.obter("janela.maximizada", False))

    def mostrar(self) -> None:
        self.showMaximized() if self._iniciar_maximizada else self.show()

    def salvar_geometria(self) -> None:
        g = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.hub.config.atualizar({
            "janela.x": g.x(), "janela.y": g.y(),
            "janela.largura": g.width(), "janela.altura": g.height(),
            "janela.maximizada": self.isMaximized(),
        }, silencioso=True)

    def closeEvent(self, evento):  # noqa: N802
        self.salvar_geometria()
        if self.hub.config.obter("geral.fechar_para_bandeja", False) and self.hub.bandeja_disponivel():
            evento.ignore()
            self.hide()
            self.hub.notificar(NOME_APP, tr("O Hub continua rodando na bandeja."))
            return
        evento.ignore()  # o HubApp encerra tudo na ordem certa
        self.hub.sair()
