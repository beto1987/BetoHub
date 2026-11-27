"""Orquestrador do StarHub: monta tudo na ordem certa e encerra com segurança.

Ordem de inicialização:
 1. pastas e logs
 2. QApplication + trava de instância única
 3. configuração (config.toml) + tema
 4. banco SQLite, eventos, tarefas
 5. overlay e bandeja
 6. plugins (migrações + setup), abas e painéis do overlay
 7. atalho global (se ativo)
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QLockFile, QObject, QPointF, QProcess, QTranslator
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from beto_hub.core.i18n import N_, tr
from . import NOME_APP, __version__
from .core import i18n, keymap, paths
from .core.config import GerenciadorConfig
from .core.database import BancoDados
from .core.events import BarramentoEventos
from .core.hotkeys import GerenciadorAtalhos
from .core.logging_setup import configurar_logs, definir_nivel, obter_logger
from .core.plugin_base import HubContext, Manifesto
from .core.plugin_loader import OK, CarregadorPlugins, PluginCarregado
from .core.workers import GerenciadorTarefas
from .services.api_cache import MIGRACOES_NUCLEO, CacheAPI
from .services.http_client import ClienteHTTP, LimitadorTaxa
from .services.uex_api import ClienteUEX
from .services.wiki_api import ClienteWiki
from .ui.main_window import JanelaPrincipal
from .ui.overlay import JanelaOverlay
from .ui.settings_dialog import DialogoConfiguracoes
from .ui.theme import CORES, aplicar_tema
from .ui.widgets.campos import instalar_dicas_discretas

# Atalhos globais: nome lógico -> (chave da combinação, chave do liga/desliga) no config
ATALHO_OVERLAY = "overlay"
ATALHO_CLIQUE = "clique"
ATALHOS = {
    ATALHO_OVERLAY: ("atalhos.overlay", "atalhos.overlay_ativo"),
    ATALHO_CLIQUE: ("atalhos.clique", "atalhos.clique_ativo"),
}
NOMES_ATALHOS = {ATALHO_OVERLAY: N_("mostrar/esconder overlay"), ATALHO_CLIQUE: N_("clique atravessa")}


def _icone_app() -> QIcon:
    """Usa icone.ico do tema; se não existir, desenha um losango ciano."""
    arquivo = paths.pasta_tema() / "icone.ico"
    if arquivo.exists():
        return QIcon(str(arquivo))
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor(CORES["acento"]))
    p.setBrush(QColor(CORES["acento_escuro"]))
    p.drawPolygon(QPolygonF([QPointF(32, 4), QPointF(60, 32), QPointF(32, 60), QPointF(4, 32)]))
    p.end()
    return QIcon(pix)


class HubApp(QObject):
    def __init__(self, argv: list[str]):
        super().__init__()
        # 1) pastas e logs (nível definitivo é lido do config logo abaixo)
        paths.garantir_pastas()
        self.log = configurar_logs(paths.pasta_logs())
        self.log.info("=== %s v%s iniciando (Python %s) ===", NOME_APP, __version__, sys.version.split()[0])
        for copia in paths.MIGRADAS:
            self.log.info("Dados do Beto Hub copiados: %s", copia)

        # 2) Qt
        self.qt = QApplication(argv)
        self.qt.setApplicationName(NOME_APP)
        self.qt.setApplicationVersion(__version__)
        self.qt.setQuitOnLastWindowClosed(False)  # overlay/bandeja seguem vivos
        self.qt.setWindowIcon(_icone_app())
        # Traduções do próprio Qt (botões Sim/Não, menus de contexto) no idioma escolhido
        self._tradutor_qt = QTranslator(self.qt)
        if self._tradutor_qt.load(i18n.ARQUIVOS_QT.get(i18n.idioma(), ""),
                                  QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
            self.qt.installTranslator(self._tradutor_qt)
        # Números e datas dos campos do Qt (spinbox, data) no padrão do idioma
        QLocale.setDefault(QLocale(i18n.LOCALES_QT.get(i18n.idioma(), "pt_BR")))
        self.log.info("Idioma da interface: %s", i18n.idioma())
        self._trava = QLockFile(str(paths.pasta_dados() / "starhub.lock"))
        self._trava.setStaleLockTime(0)  # sem prazo; trava de processo que morreu é detectada pelo PID

        self._encerrando = False
        # nome do atalho -> (ok, mensagem) do último registro
        self.status_atalhos: dict[str, tuple[bool, str]] = {n: (False, tr("Atalho desativado.")) for n in ATALHOS}
        self.plugins: list[PluginCarregado] = []

    # ================================================================ início
    def executar(self) -> int:
        if not self._trava.tryLock(200):
            QMessageBox.information(None, NOME_APP, tr("O StarHub já está aberto (veja a bandeja do Windows)."))
            self.log.warning("Segunda instância bloqueada")
            return 0

        try:
            self._montar()
        except Exception as erro:
            self.log.critical("Falha ao iniciar o Hub", exc_info=True)
            QMessageBox.critical(
                None, NOME_APP,
                tr("O Hub não conseguiu iniciar:\n{erro}\n\nDetalhes no log:\n{pasta}", erro=erro, pasta=paths.pasta_logs()),
            )
            return 1
        return self.qt.exec()

    def _montar(self) -> None:
        # 3) configuração + tema
        self.config = GerenciadorConfig(paths.arquivo_config())
        if i18n.PENDENTE_DA_INSTALACAO:  # idioma escolhido no instalador: salva uma vez
            codigo, marca = i18n.PENDENTE_DA_INSTALACAO
            self.config.atualizar({"geral.idioma": codigo, "geral.idioma_instalador": marca}, silencioso=True)
            self.log.info("Idioma escolhido no instalador: %s", codigo)
        definir_nivel(self.config.obter("geral.nivel_log", "INFO"))
        aplicar_tema(self.qt)
        self._filtro_dicas = instalar_dicas_discretas(self.qt)  # dicas somem ao clicar e voltam ao sair

        # 4) serviços do núcleo
        self.banco = BancoDados(paths.arquivo_banco())
        self.eventos = BarramentoEventos()
        self.workers = GerenciadorTarefas()
        self.banco.migrar("nucleo", MIGRACOES_NUCLEO)
        self.cache_api = CacheAPI(self.banco)
        # Serviços compartilhados, acessíveis pelos módulos via ctx.servico("nome")
        self.servicos: dict = {
            "cache": self.cache_api,
            "uex": ClienteUEX(ClienteHTTP(), self.cache_api, self.config.obter),
            "wiki": ClienteWiki(ClienteHTTP(LimitadorTaxa(30), timeout=40.0), self.cache_api),
        }

        # 5) overlay e bandeja
        self.overlay = JanelaOverlay(self.config)
        self._criar_bandeja()

        # 6) plugins
        carregador = CarregadorPlugins(paths.pasta_plugins(), self.config.obter("plugins.desativados", []))
        self.plugins = carregador.carregar_todos(self._criar_contexto, self.banco.migrar)
        self._montar_overlay()
        self.janela = JanelaPrincipal(self)

        # 7) atalhos e reações a mudanças de configuração
        self.atalhos = GerenciadorAtalhos()
        self.atalhos.acionado.connect(self._ao_atalho)
        self._aplicar_atalhos()
        self.config.alterado.connect(self._ao_mudar_config)
        self.overlay.visibilidadeAlterada.connect(lambda *_: self._atualizar_status())
        # Módulos podem pedir para trazer a janela e abrir a aba de outro módulo
        self.eventos.assinar("hub.mostrar_aba", self._mostrar_aba)

        self.janela.mostrar()
        if self.config.obter("overlay.mostrar_ao_iniciar", False):
            self.overlay.show()
        self._atualizar_status()

        if self.config.aviso_carga:
            QMessageBox.warning(self.janela, NOME_APP, self.config.aviso_carga)
        self.log.info("Hub pronto: %d módulo(s) ativo(s)", sum(p.estado == OK for p in self.plugins))

    def _criar_contexto(self, manifesto: Manifesto) -> HubContext:
        pasta = paths.pasta_dados() / "modulos" / manifesto.id
        pasta.mkdir(parents=True, exist_ok=True)
        return HubContext(
            manifesto=manifesto,
            config=self.config,
            banco=self.banco,
            eventos=self.eventos,
            workers=self.workers,
            log=obter_logger(f"plugin.{manifesto.id}"),
            notificar=self.notificar,
            pasta_dados=pasta,
            servicos=self.servicos,
        )

    def _montar_overlay(self) -> None:
        for plugin in self.plugins:
            if plugin.estado != OK:
                continue
            try:
                painel = plugin.instancia.criar_painel_overlay()
            except Exception:
                self.log.exception("Erro ao criar o painel de overlay de %s", plugin.id)
                continue
            if painel is not None:
                self.overlay.adicionar_painel(plugin.id, tr(plugin.nome), painel)
        self.overlay.finalizar_paineis()

    # ================================================================ bandeja
    def _criar_bandeja(self) -> None:
        self.bandeja = QSystemTrayIcon(self.qt.windowIcon(), self)
        self.bandeja.setToolTip(NOME_APP)
        menu = QMenu()
        menu.addAction(tr("Abrir StarHub"), self.mostrar_janela)
        menu.addAction(tr("Mostrar/esconder overlay"), self.alternar_overlay)
        self.acao_bandeja_clique = QAction(tr("Overlay: clique atravessa"), menu, checkable=True)
        self.acao_bandeja_clique.triggered.connect(lambda *_: self.alternar_clique_atravessa())
        menu.addAction(self.acao_bandeja_clique)
        menu.addSeparator()
        menu.addAction(tr("Configurações…"), self.abrir_configuracoes)
        menu.addSeparator()
        menu.addAction(tr("Sair"), self.sair)
        self._menu_bandeja = menu  # manter referência
        self.bandeja.setContextMenu(menu)
        self.bandeja.activated.connect(
            lambda motivo: self.mostrar_janela() if motivo == QSystemTrayIcon.DoubleClick else None
        )
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.bandeja.show()

    def bandeja_disponivel(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable() and self.bandeja.isVisible()

    def notificar(self, titulo: str, mensagem: str) -> None:
        """Balão do Windows (usado, por ex., para avisar que o refino ficou pronto)."""
        self.log.info("Notificação: %s — %s", titulo, mensagem)
        if self.bandeja_disponivel():
            self.bandeja.showMessage(titulo, mensagem, QSystemTrayIcon.Information, 6000)

    # ================================================================ ações
    def mostrar_janela(self) -> None:
        self.janela.showNormal() if self.janela.isMinimized() else self.janela.show()
        self.janela.raise_()
        self.janela.activateWindow()

    def alternar_overlay(self) -> None:
        self.overlay.alternar()

    def alternar_clique_atravessa(self) -> None:
        self.config.definir("overlay.clique_atravessa", not self.overlay.clique_atravessa)

    def abrir_configuracoes(self) -> None:
        self.mostrar_janela()
        # Pausa o atalho para não disparar enquanto o usuário captura uma combinação nova
        self.atalhos.pausar(True)
        try:
            DialogoConfiguracoes(self, self.janela).exec()
        finally:
            self.atalhos.pausar(False)

    def _mostrar_aba(self, id_modulo) -> None:
        self.mostrar_janela()
        self.janela.selecionar_aba(str(id_modulo))

    def _ao_atalho(self, nome: str) -> None:
        if nome == ATALHO_OVERLAY:
            self.alternar_overlay()
        elif nome == ATALHO_CLIQUE:
            self.alternar_clique_atravessa()

    # ================================================================ reações
    def _aplicar_atalhos(self) -> None:
        """(Re)registra todos os atalhos globais conforme o config. Vale na hora."""
        usados: dict[str, str] = {}  # combinação normalizada -> nome do atalho que já a usa
        for nome, (chave_texto, chave_ativo) in ATALHOS.items():
            ativo = bool(self.config.obter(chave_ativo, False))
            texto = str(self.config.obter(chave_texto, "") or "")
            if not ativo or not texto:
                self.atalhos.remover(nome)
                self.status_atalhos[nome] = (False, tr("Atalho desativado."))
                continue
            try:
                normal = keymap.normalizar(texto)
            except ValueError as erro:
                self.atalhos.remover(nome)
                self.status_atalhos[nome] = (False, str(erro))
                continue
            if normal in usados:
                self.atalhos.remover(nome)
                self.status_atalhos[nome] = (
                    False, tr("{atalho} já é o atalho de \"{nome}\". Escolha outra.", atalho=normal,
                              nome=tr(NOMES_ATALHOS[usados[normal]]))
                )
                continue
            usados[normal] = nome
            self.status_atalhos[nome] = self.atalhos.registrar(nome, texto)

    def _ao_mudar_config(self, chaves: set[str]) -> None:
        if all(c.startswith("modulos.") for c in chaves):
            return  # opções internas de módulos: cada módulo cuida das suas
        if any(c.startswith("atalhos.") for c in chaves):
            self._aplicar_atalhos()
        if chaves & {"overlay.opacidade", "overlay.clique_atravessa"}:
            self.overlay.aplicar_config()
        if "geral.nivel_log" in chaves:
            definir_nivel(self.config.obter("geral.nivel_log", "INFO"))
            self.log.info("Nível de log alterado para %s", self.config.obter("geral.nivel_log"))
        self._atualizar_status()
        self.janela.mensagem(tr("Configurações aplicadas."))

    def _atualizar_status(self) -> None:
        if not hasattr(self, "janela"):
            return
        visivel = self.overlay.isVisible()
        clique = self.overlay.clique_atravessa
        self.janela.atualizar_status(
            visivel, clique,
            self.atalhos.texto_ativo(ATALHO_OVERLAY), self.atalhos.texto_ativo(ATALHO_CLIQUE),
        )
        self.acao_bandeja_clique.setChecked(clique)

    # ================================================================ saída
    def reiniciar(self) -> None:
        """Fecha e abre o Hub de novo (usado para trocar o idioma)."""
        if getattr(sys, "frozen", False):
            programa, argumentos = sys.executable, sys.argv[1:]
        else:
            programa, argumentos = sys.executable, [str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]
        self.log.info("Reiniciando o Hub")
        self.sair()  # libera a trava de instância única antes de abrir o novo processo
        QProcess.startDetached(programa, argumentos, str(paths.raiz_app()))

    def sair(self) -> None:
        if self._encerrando:
            return
        self._encerrando = True
        self.log.info("Encerrando o Hub…")
        try:
            self.janela.salvar_geometria()
        except Exception:
            self.log.exception("Erro ao salvar a geometria da janela")
        for plugin in self.plugins:
            if plugin.estado == OK:
                try:
                    plugin.instancia.encerrar()
                except Exception:
                    self.log.exception("Erro ao encerrar o módulo %s", plugin.id)
        self.atalhos.remover_todos()
        self.workers.aguardar(3000)
        self.banco.fechar()
        self.bandeja.hide()
        self.overlay.close()
        self._trava.unlock()
        self.log.info("=== Hub encerrado ===")
        self.qt.quit()


def main() -> int:
    return HubApp(sys.argv).executar()
