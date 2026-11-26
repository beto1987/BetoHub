"""Seção "Contratos" na tela de Configurações: leitura do Game.log e pasta do jogo."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget,
)

from ..logica.arquivos import NOME_LOG, PASTA_BACKUPS, detectar_pasta


class PainelConfigContratos(QWidget):
    def __init__(self, ler_log: bool, pasta: str, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)

        self.ler_log = QCheckBox("Ler o Game.log do Star Citizen para acompanhar os contratos")
        self.ler_log.setChecked(ler_log)
        form.addRow(self.ler_log)

        linha = QHBoxLayout()
        self.pasta = QLineEdit(pasta)
        detectada = detectar_pasta()
        self.pasta.setPlaceholderText(f"automático: {detectada}" if detectada else "pasta não encontrada")
        linha.addWidget(self.pasta, 1)
        procurar = QPushButton("Procurar…")
        procurar.clicked.connect(self._procurar)
        linha.addWidget(procurar)
        form.addRow("Pasta do jogo:", linha)

        self.aviso = QLabel()
        self.aviso.setWordWrap(True)
        form.addRow(self.aviso)
        self.pasta.textChanged.connect(self._conferir)
        self._conferir()

        ajuda = QLabel(
            "O Hub só LÊ o arquivo de texto que o jogo grava (Game.log) e os logs das sessões anteriores "
            f"(pasta {PASTA_BACKUPS}). Nada é alterado na pasta do jogo.\n\n"
            "Deixe a pasta em branco para detectar sozinho (canal LIVE). Para o PTU, escolha a pasta "
            "...\\StarCitizen\\PTU.")
        ajuda.setWordWrap(True)
        ajuda.setProperty("papel", "ajuda")
        form.addRow(ajuda)

    def _procurar(self) -> None:
        inicial = self.pasta.text() or str(detectar_pasta() or "C:/")
        escolhida = QFileDialog.getExistingDirectory(self, "Pasta do Star Citizen (LIVE, PTU…)", inicial)
        if escolhida:
            self.pasta.setText(str(Path(escolhida)))

    def _conferir(self) -> None:
        texto = self.pasta.text().strip()
        pasta = Path(texto) if texto else detectar_pasta()
        if pasta and ((pasta / NOME_LOG).is_file() or (pasta / PASTA_BACKUPS).is_dir()):
            self.aviso.setText(f"✔ Logs encontrados em {pasta}")
            self.aviso.setProperty("papel", "ok")
        else:
            self.aviso.setText("✕ Não encontrei Game.log nem logbackups nessa pasta.")
            self.aviso.setProperty("papel", "erro")
        self.aviso.style().unpolish(self.aviso)
        self.aviso.style().polish(self.aviso)
