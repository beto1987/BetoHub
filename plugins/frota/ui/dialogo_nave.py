"""Janela para adicionar ou editar uma nave do hangar."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout,
)

from beto_hub.ui.theme import repolir

from ..logica.comparacao import numero
from ..logica.hangar import ORIGENS, NaveHangar
from ..logica.naves import FichaNave
from .comum import combo_pesquisavel, preencher_naves


class DialogoNave(QDialog):
    def __init__(self, fichas: list[FichaNave], nave: NaveHangar | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar nave" if nave else "Adicionar nave ao hangar")
        self.setMinimumWidth(460)
        self.fichas = {f.uuid: f for f in fichas}
        self.original = nave
        self.nave: NaveHangar | None = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.combo = QComboBox()
        combo_pesquisavel(self.combo)
        preencher_naves(self.combo, fichas, manter_uuid=nave.uuid if nave else "")
        self.combo.setToolTip("Digite parte do nome para filtrar.")
        self.combo.currentIndexChanged.connect(self._resumo)
        form.addRow("Nave:", self.combo)

        self.resumo = QLabel()
        self.resumo.setProperty("papel", "ajuda")
        self.resumo.setWordWrap(True)
        form.addRow("", self.resumo)

        self.apelido = QLineEdit(nave.apelido if nave else "")
        self.apelido.setPlaceholderText("Opcional. Ex.: \"Carga pesada\"")
        form.addRow("Apelido:", self.apelido)

        self.origem = QComboBox()
        self.origem.setEditable(True)
        self.origem.addItems(ORIGENS)
        self.origem.setCurrentText(nave.origem if nave else ORIGENS[0])
        form.addRow("Origem:", self.origem)

        self.notas = QPlainTextEdit(nave.notas if nave else "")
        self.notas.setPlaceholderText("Opcional. Ex.: pintura, seguro, onde está guardada…")
        self.notas.setFixedHeight(70)
        form.addRow("Notas:", self.notas)
        layout.addLayout(form)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Ok).setText("Salvar")
        botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botoes.accepted.connect(self._salvar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)
        self._resumo()

    def _ficha(self) -> FichaNave | None:
        return self.fichas.get(self.combo.currentData() or "")

    def _resumo(self) -> None:
        f = self._ficha()
        if not f:
            self.resumo.setText("Escolha uma nave da lista.")
            return
        partes = [f.fabricante, f.funcao or f.carreira_pt,
                  f"{numero(f.carga_scu)} SCU" if f.carga_scu else "",
                  f"DPS {numero(f.dps_total)}" if f.dps_total else ""]
        self.resumo.setText(" · ".join(p for p in partes if p))

    def _salvar(self) -> None:
        f = self._ficha()
        if not f:
            self.resumo.setText("Escolha uma nave da lista antes de salvar.")
            self.resumo.setProperty("papel", "erro")
            repolir(self.resumo)
            return
        self.nave = NaveHangar(
            id=self.original.id if self.original else None, uuid=f.uuid, nome=f.nome,
            apelido=self.apelido.text(), origem=self.origem.currentText().strip(),
            notas=self.notas.toPlainText(),
        )
        self.accept()
