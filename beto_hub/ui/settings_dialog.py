"""Tela de Configurações.

Tudo é salvo no config.toml. Ao clicar em Aplicar/OK o GerenciadorConfig
emite `alterado` e o HubApp reage na hora: re-registra o atalho, ajusta o
overlay e o nível de log — sem reiniciar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSlider,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from beto_hub.core.i18n import N_, tr
from ..core import i18n, keymap, paths
from ..core.logging_setup import NIVEIS_VALIDOS, obter_logger
from ..core.plugin_loader import DESATIVADO, ERRO, OK
from .widgets import CampoAtalho

if TYPE_CHECKING:
    from ..app import HubApp

log = obter_logger("configuracoes")


def _ajuda(texto: str) -> QLabel:
    rotulo = QLabel(texto)
    rotulo.setWordWrap(True)
    rotulo.setProperty("papel", "ajuda")
    return rotulo


class DialogoConfiguracoes(QDialog):
    def __init__(self, hub: "HubApp", parent=None):
        super().__init__(parent)
        self.hub = hub
        self.cfg = hub.config
        self.setWindowTitle(tr("Configurações — StarHub"))
        self.setMinimumSize(640, 520)

        # Valores do overlay antes de abrir, para desfazer a prévia ao cancelar
        self._opacidade_original = float(self.cfg.obter("overlay.opacidade", 0.85))

        self.abas = QTabWidget()
        self.abas.addTab(self._aba_geral(), tr("GERAL"))
        self.abas.addTab(self._aba_atalhos(), tr("ATALHOS"))
        self.abas.addTab(self._aba_overlay(), tr("OVERLAY"))
        self.abas.addTab(self._aba_api(), "API")
        self.abas.addTab(self._aba_modulos(), tr("MÓDULOS"))
        self._paineis_plugins = self._abas_dos_plugins()

        botoes = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        botoes.button(QDialogButtonBox.Ok).setText("OK")
        botoes.button(QDialogButtonBox.Cancel).setText(tr("Cancelar"))
        botoes.button(QDialogButtonBox.Apply).setText(tr("Aplicar"))
        botoes.button(QDialogButtonBox.Ok).setProperty("destaque", "true")
        botoes.accepted.connect(self._ok)
        botoes.rejected.connect(self.reject)
        botoes.button(QDialogButtonBox.Apply).clicked.connect(self._aplicar)

        layout = QVBoxLayout(self)
        layout.addWidget(self.abas, 1)
        layout.addWidget(botoes)

    # ================================================================ abas
    def _aba_geral(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.idioma = QComboBox()
        for codigo, nome in i18n.IDIOMAS.items():
            self.idioma.addItem(nome, codigo)
        self._idioma_original = str(self.cfg.obter("geral.idioma", i18n.PADRAO))
        self.idioma.setCurrentIndex(max(0, self.idioma.findData(self._idioma_original)))
        form.addRow(tr("Idioma:"), self.idioma)
        form.addRow("", _ajuda(tr("O idioma muda quando o Hub é reaberto.")))

        self.nivel_log = QComboBox()
        for nivel in NIVEIS_VALIDOS:
            self.nivel_log.addItem(nivel, nivel)
        self.nivel_log.setCurrentIndex(max(0, self.nivel_log.findData(self.cfg.obter("geral.nivel_log", "INFO"))))
        form.addRow(tr("Nível de log:"), self.nivel_log)

        self.fechar_bandeja = QCheckBox(tr("Ao fechar a janela, continuar rodando na bandeja"))
        self.fechar_bandeja.setChecked(bool(self.cfg.obter("geral.fechar_para_bandeja", False)))
        form.addRow("", self.fechar_bandeja)

        linha = QHBoxLayout()
        for texto, caminho in ((tr("Abrir config.toml"), paths.arquivo_config()),
                               (tr("Abrir pasta de logs"), paths.pasta_logs())):
            botao = QPushButton(texto)
            botao.clicked.connect(lambda *_, c=caminho: QDesktopServices.openUrl(QUrl.fromLocalFile(str(c))))
            linha.addWidget(botao)
        linha.addStretch(1)
        form.addRow("", linha)
        form.addRow("", _ajuda(tr("Configuração: {config}\nDados e logs: {dados}",
                                  config=paths.arquivo_config(), dados=paths.pasta_dados())))
        return w

    # Atalhos globais mostrados na tela: nome lógico -> (título, chave do texto, chave do liga/desliga)
    _ATALHOS = {
        "overlay": (N_("MOSTRAR / ESCONDER O OVERLAY"), "atalhos.overlay", "atalhos.overlay_ativo"),
        "clique": (N_("LIGAR / DESLIGAR O CLIQUE ATRAVESSA"), "atalhos.clique", "atalhos.clique_ativo"),
    }

    def _aba_atalhos(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        # nome -> (checkbox, campo, rótulo de situação)
        self._campos_atalho: dict[str, tuple[QCheckBox, CampoAtalho, QLabel]] = {}

        for nome, (titulo, chave_texto, chave_ativo) in self._ATALHOS.items():
            grupo = QGroupBox(tr(titulo))
            form = QFormLayout(grupo)

            ativo = QCheckBox(tr("Ativar atalho global"))
            ativo.setChecked(bool(self.cfg.obter(chave_ativo, False)))
            form.addRow("", ativo)

            campo = CampoAtalho(str(self.cfg.obter(chave_texto, "")))
            limpar = QPushButton(tr("Limpar"))
            limpar.clicked.connect(lambda *_, c=campo: c.definir_valor(""))
            linha = QHBoxLayout()
            linha.addWidget(campo, 1)
            linha.addWidget(limpar)
            form.addRow(tr("Combinação:"), linha)

            situacao = QLabel()
            situacao.setWordWrap(True)
            form.addRow(tr("Situação:"), situacao)

            ativo.toggled.connect(lambda v, c=campo, b=limpar: (c.setEnabled(v), b.setEnabled(v)))
            campo.setEnabled(ativo.isChecked())
            limpar.setEnabled(ativo.isChecked())
            self._campos_atalho[nome] = (ativo, campo, situacao)
            layout.addWidget(grupo)

        self._atualizar_status_atalhos()
        layout.addWidget(_ajuda(tr(
            "Clique no campo e pressione a combinação. Esc cancela, Backspace limpa.\n\n"
            "Os atalhos funcionam também com o Star Citizen em foco. As teclas continuam chegando "
            "ao jogo, então prefira combinações que não fazem nada nele (ex.: Ctrl+Shift+F10 e "
            "Ctrl+Shift+F11). Os dois atalhos precisam ser diferentes.\n"
            "A mudança vale assim que você clicar em Aplicar ou OK. "
            "Enquanto esta tela estiver aberta, os atalhos ficam pausados."
        )))
        layout.addStretch(1)
        return w

    def _aba_overlay(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        linha = QHBoxLayout()
        self.opacidade = QSlider(Qt.Horizontal)
        self.opacidade.setRange(20, 100)
        self.opacidade.setValue(round(self._opacidade_original * 100))
        rotulo = QLabel(f"{self.opacidade.value()}%")
        rotulo.setMinimumWidth(40)

        def ao_mover(valor: int) -> None:
            rotulo.setText(f"{valor}%")
            self.hub.overlay.definir_opacidade(valor / 100)  # prévia ao vivo

        self.opacidade.valueChanged.connect(ao_mover)
        linha.addWidget(self.opacidade, 1)
        linha.addWidget(rotulo)
        form.addRow(tr("Opacidade:"), linha)

        self.clique_atravessa = QCheckBox(tr("Cliques atravessam o overlay e vão para o jogo"))
        self.clique_atravessa.setChecked(bool(self.cfg.obter("overlay.clique_atravessa", False)))
        form.addRow("", self.clique_atravessa)

        self.mostrar_ao_iniciar = QCheckBox(tr("Mostrar o overlay quando o Hub abrir"))
        self.mostrar_ao_iniciar.setChecked(bool(self.cfg.obter("overlay.mostrar_ao_iniciar", False)))
        form.addRow("", self.mostrar_ao_iniciar)

        form.addRow("", _ajuda(tr(
            "Com \"clique atravessa\" ligado não dá para clicar no overlay. Desligue pelo menu "
            "Exibir, pelo ícone da bandeja ou aqui.\n"
            "O overlay aparece por cima do jogo em modo \"Janela sem bordas\" (Borderless)."
        )))
        return w

    def _aba_api(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.token = QLineEdit(str(self.cfg.obter("api.uex_token", "")))
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText(tr("Cole aqui o token do seu app na UEX"))
        mostrar = QCheckBox(tr("Mostrar"))
        mostrar.toggled.connect(
            lambda v: self.token.setEchoMode(QLineEdit.Normal if v else QLineEdit.Password)
        )
        linha = QHBoxLayout()
        linha.addWidget(self.token, 1)
        linha.addWidget(mostrar)
        form.addRow(tr("Token UEX:"), linha)

        self.url_uex = QLineEdit(str(self.cfg.obter("api.uex_url", "https://api.uexcorp.uk/2.0")))
        form.addRow(tr("Endereço da API:"), self.url_uex)

        self.auto_atualizar = QCheckBox(tr("Atualizar dados automaticamente"))
        self.auto_atualizar.setChecked(bool(self.cfg.obter("api.atualizacao_automatica", True)))
        form.addRow("", self.auto_atualizar)

        self.intervalo = QSpinBox()
        self.intervalo.setRange(5, 240)
        self.intervalo.setSuffix(" min")
        self.intervalo.setValue(int(self.cfg.obter("api.intervalo_minutos", 15)))
        form.addRow(tr("Intervalo:"), self.intervalo)

        form.addRow("", _ajuda(tr(
            "O token é criado no site da UEX Corp, na página \"My Apps\". "
            "Ele fica salvo em texto puro no config.toml — não compartilhe esse arquivo.\n"
            "A UEX permite até 120 requisições por minuto; o Hub usa cache e fica abaixo de 100."
        )))
        return w

    def _aba_modulos(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.lista_modulos = QListWidget()
        textos = {OK: tr("carregado"), ERRO: tr("com erro"), DESATIVADO: tr("desativado")}
        for plugin in self.hub.plugins:
            versao = f" v{plugin.manifesto.versao}" if plugin.manifesto else ""
            item = QListWidgetItem(f"{tr(plugin.nome)}{versao}  —  {textos.get(plugin.estado, plugin.estado)}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if plugin.estado == DESATIVADO else Qt.Checked)
            item.setData(Qt.UserRole, plugin.id)
            if plugin.erro:
                item.setToolTip(plugin.erro)
            self.lista_modulos.addItem(item)
        layout.addWidget(self.lista_modulos, 1)
        layout.addWidget(_ajuda(tr("Ativar ou desativar módulos vale a partir da próxima vez que o Hub abrir.")))
        return w

    def _abas_dos_plugins(self) -> list[tuple[Any, QWidget]]:
        paineis = []
        for plugin in self.hub.plugins:
            if plugin.estado != OK:
                continue
            try:
                painel = plugin.instancia.criar_painel_config()
            except Exception:
                log.exception("Erro ao criar o painel de configuração de %s", plugin.id)
                continue
            if painel is not None:
                self.abas.addTab(painel, tr(plugin.nome).upper())
                paineis.append((plugin, painel))
        return paineis

    # ================================================================ ações
    def _atualizar_status_atalhos(self) -> None:
        for nome, (ativo, _campo, situacao) in self._campos_atalho.items():
            ok, msg = self.hub.status_atalhos.get(nome, (False, tr("Atalho desativado.")))
            situacao.setText(msg)
            situacao.setProperty("papel", "ok" if ok else ("erro" if ativo.isChecked() else "ajuda"))
            situacao.style().unpolish(situacao)
            situacao.style().polish(situacao)

    def _coletar(self) -> dict[str, Any]:
        desativados = [
            self.lista_modulos.item(i).data(Qt.UserRole)
            for i in range(self.lista_modulos.count())
            if self.lista_modulos.item(i).checkState() == Qt.Unchecked
        ]
        valores: dict[str, Any] = {}
        for nome, (ativo, campo, _) in self._campos_atalho.items():
            _, chave_texto, chave_ativo = self._ATALHOS[nome]
            valores[chave_ativo] = ativo.isChecked()
            valores[chave_texto] = campo.valor()
        return valores | {
            "geral.idioma": self.idioma.currentData(),
            "geral.nivel_log": self.nivel_log.currentData(),
            "geral.fechar_para_bandeja": self.fechar_bandeja.isChecked(),
            "overlay.opacidade": round(self.opacidade.value() / 100, 2),
            "overlay.clique_atravessa": self.clique_atravessa.isChecked(),
            "overlay.mostrar_ao_iniciar": self.mostrar_ao_iniciar.isChecked(),
            "api.uex_token": self.token.text().strip(),
            "api.uex_url": self.url_uex.text().strip().rstrip("/"),
            "api.atualizacao_automatica": self.auto_atualizar.isChecked(),
            "api.intervalo_minutos": self.intervalo.value(),
            "plugins.desativados": desativados,
        }

    def _validar(self, valores: dict[str, Any]) -> str | None:
        usados: dict[str, str] = {}
        for nome, (titulo, chave_texto, chave_ativo) in self._ATALHOS.items():
            if not valores[chave_ativo]:
                continue
            titulo = tr(titulo).capitalize()
            if not valores[chave_texto]:
                return tr("{titulo}: escolha uma combinação ou desmarque \"Ativar atalho global\".", titulo=titulo)
            try:
                normal = keymap.normalizar(valores[chave_texto])
            except ValueError as erro:
                return tr("{titulo}: atalho inválido ({erro})", titulo=titulo, erro=erro)
            if normal in usados:
                return tr("Os dois atalhos estão com a mesma combinação ({atalho}). Escolha combinações diferentes.",
                          atalho=normal)
            usados[normal] = nome
        if not valores["api.uex_url"].startswith(("http://", "https://")):
            return tr("O endereço da API precisa começar com https://")
        return None

    def _aplicar(self) -> bool:
        valores = self._coletar()
        problema = self._validar(valores)
        if problema:
            QMessageBox.warning(self, tr("Configurações"), problema)
            return False
        try:
            self.cfg.atualizar(valores)  # dispara a reação do HubApp (atalho, overlay, log)
        except OSError as erro:
            QMessageBox.critical(self, tr("Configurações"), tr("Não foi possível salvar o arquivo:\n{erro}", erro=erro))
            return False
        self._opacidade_original = valores["overlay.opacidade"]

        for plugin, painel in self._paineis_plugins:
            try:
                plugin.instancia.aplicar_config(painel)
            except Exception:
                log.exception("Erro ao aplicar as configurações do módulo %s", plugin.id)

        self._atualizar_status_atalhos()
        for nome, (titulo, _, chave_ativo) in self._ATALHOS.items():
            ok, msg = self.hub.status_atalhos.get(nome, (False, ""))
            if valores[chave_ativo] and not ok:
                QMessageBox.warning(self, tr("Atalho"), f"{tr(titulo).capitalize()}: {msg}")
                self.abas.setCurrentIndex(1)
                return False
        return True

    def _ok(self) -> None:
        if self._aplicar():
            self.accept()
            self._oferecer_reinicio()

    def _oferecer_reinicio(self) -> None:
        """O idioma só muda ao reabrir o Hub: pergunta se pode reiniciar agora."""
        novo = self.idioma.currentData()
        if novo == self._idioma_original:
            return
        self._idioma_original = novo
        # A pergunta já sai no idioma novo, para quem acabou de escolhê-lo
        atual = i18n.idioma()
        i18n.definir_idioma(novo)
        titulo, texto = tr("Idioma"), tr("Reiniciar o Hub agora para mudar o idioma?")
        i18n.definir_idioma(atual)
        if QMessageBox.question(self.parentWidget() or self, titulo, texto) == QMessageBox.Yes:
            self.hub.reiniciar()

    def reject(self) -> None:
        # Desfaz a prévia de opacidade se o usuário cancelar
        self.hub.overlay.definir_opacidade(self._opacidade_original)
        super().reject()
