"""Aplica o tema escuro sci-fi (paleta + folha de estilo QSS)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from ...core.logging_setup import obter_logger
from ...core.paths import pasta_tema

log = obter_logger("tema")

# Paleta central — mude aqui para mudar o app inteiro.
CORES = {
    "fundo": "#070b12",
    "painel": "#0d1520",
    "painel2": "#121d2b",
    "borda": "#1e3a52",
    "acento": "#35c8f5",        # ciano HUD
    "acento_escuro": "#0f3a4f",
    "alerta": "#f5a623",        # âmbar
    "perigo": "#ff5c5c",
    "ok": "#4cd98a",
    "texto": "#d6e6f2",
    "texto_suave": "#7f98ad",
}

# Bahnschrift vem no Windows 10/11 e tem cara de painel de nave.
FONTES_PREFERIDAS = ("Bahnschrift", "Segoe UI", "Arial")


def _escolher_fonte() -> str:
    disponiveis = set(QFontDatabase.families())
    for nome in FONTES_PREFERIDAS:
        if nome in disponiveis:
            return nome
    return QApplication.font().family()


def aplicar_tema(app: QApplication) -> None:
    app.setStyle("Fusion")  # base neutra que respeita bem o QSS

    paleta = QPalette()
    c = {k: QColor(v) for k, v in CORES.items()}
    paleta.setColor(QPalette.Window, c["fundo"])
    paleta.setColor(QPalette.WindowText, c["texto"])
    paleta.setColor(QPalette.Base, c["fundo"])
    paleta.setColor(QPalette.AlternateBase, c["painel"])
    paleta.setColor(QPalette.Text, c["texto"])
    paleta.setColor(QPalette.Button, c["painel2"])
    paleta.setColor(QPalette.ButtonText, c["texto"])
    paleta.setColor(QPalette.Highlight, c["acento_escuro"])
    paleta.setColor(QPalette.HighlightedText, c["acento"])
    paleta.setColor(QPalette.ToolTipBase, c["painel2"])
    paleta.setColor(QPalette.ToolTipText, c["texto"])
    paleta.setColor(QPalette.PlaceholderText, c["texto_suave"])
    paleta.setColor(QPalette.Link, c["acento"])
    app.setPalette(paleta)

    fonte = _escolher_fonte()
    app.setFont(QFont(fonte, 10))

    arquivo = pasta_tema() / "scifi.qss"
    try:
        qss = arquivo.read_text(encoding="utf-8")
    except OSError:
        log.exception("Folha de estilo não encontrada: %s (seguindo sem ela)", arquivo)
        return
    for chave, valor in {**CORES, "fonte": fonte}.items():
        qss = qss.replace("{{" + chave + "}}", valor)
    app.setStyleSheet(qss)
    log.info("Tema aplicado (fonte: %s)", fonte)


def repolir(widget) -> None:
    """Reaplica o estilo depois de mudar uma propriedade usada no QSS."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
