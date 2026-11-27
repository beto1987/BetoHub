"""Editor da nave mineradora: nave, cabeça de cada laser e até 3 módulos."""

from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from beto_hub.core.i18n import N_, tr
from ..logica.quebra import DadosMineracao

NENHUM = N_("(nenhum)")
# Tipo de módulo como vem do mining_data.json (em português)
TIPOS_MODULO = {"passivo": N_("passivo"), "ativo": N_("ativo")}


class EditorNave(QWidget):
    alterado = Signal(dict)  # loadout novo

    def __init__(self, dados: DadosMineracao, loadout: dict[str, Any], parent=None):
        super().__init__(parent)
        self.dados = dados
        self.lo = copy.deepcopy(dados.normalizar(loadout))
        self._montando = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.nave = QComboBox()
        self.nave.addItems(list(dados.naves))
        self.nave.setCurrentText(self.lo["ship"])
        self.nave.currentTextChanged.connect(self._ao_trocar_nave)
        form.addRow(tr("Nave:"), self.nave)
        layout.addLayout(form)

        self.area_lasers = QVBoxLayout()
        layout.addLayout(self.area_lasers)
        dica = QLabel(tr("Módulos ativos (Surge, Stampede…) só contam quando você ativa; "
                         "o resultado mostra com e sem eles."))
        dica.setWordWrap(True)
        dica.setProperty("papel", "ajuda")
        layout.addWidget(dica)
        self._montar_lasers()

    def definir(self, loadout: dict[str, Any]) -> None:
        self.lo = copy.deepcopy(self.dados.normalizar(loadout))
        self._montando = True
        self.nave.setCurrentText(self.lo["ship"])
        self._montando = False
        self._montar_lasers()

    # ------------------------------------------------------------ montagem
    def _rotulo_modulo(self, nome: str) -> str:
        tipo = self.dados.modulos[nome]["type"]
        return f"{nome} ({tr(TIPOS_MODULO.get(tipo, tipo))})"

    def _montar_lasers(self) -> None:
        self._montando = True
        while self.area_lasers.count():
            item = self.area_lasers.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._linhas: list[tuple[QComboBox, list[QComboBox]]] = []
        n = len(self.lo["lasers"])
        for i, laser in enumerate(self.lo["lasers"]):
            grupo = QGroupBox(f"LASER {i + 1}" if n > 1 else tr("CABEÇA DE LASER"))
            form = QFormLayout(grupo)
            cabeca = QComboBox()
            cabeca.addItems(self.dados.cabecas_da_nave(self.lo["ship"]))
            cabeca.setCurrentText(laser["head"])
            form.addRow(tr("Cabeça:"), cabeca)
            modulos = []
            for j in range(3):
                m = QComboBox()
                m.addItem(tr(NENHUM), None)
                for nome in self.dados.modulos:
                    m.addItem(self._rotulo_modulo(nome), nome)
                atual = laser["modules"][j] if j < len(laser["modules"]) else None
                m.setCurrentIndex(max(0, m.findData(atual)))
                m.currentIndexChanged.connect(self._ao_mudar)
                form.addRow(tr("Módulo {n}:", n=j + 1), m)
                modulos.append(m)
            cabeca.currentTextChanged.connect(lambda _t, c=cabeca, ms=modulos: (self._ajustar_slots(c, ms), self._ao_mudar()))
            self._ajustar_slots(cabeca, modulos)
            self._linhas.append((cabeca, modulos))
            self.area_lasers.addWidget(grupo)
        self._montando = False

    def _ajustar_slots(self, cabeca: QComboBox, modulos: list[QComboBox]) -> None:
        slots = self.dados.cabecas.get(cabeca.currentText(), {}).get("slots", 0)
        for j, m in enumerate(modulos):
            m.setEnabled(j < slots)
            if j >= slots:
                m.setCurrentIndex(0)

    # ------------------------------------------------------------ mudanças
    def _ao_trocar_nave(self, nave: str) -> None:
        if self._montando:
            return
        self.lo = self.dados.loadout_padrao(nave)
        self._montar_lasers()
        self.alterado.emit(copy.deepcopy(self.lo))

    def _ao_mudar(self, *_a) -> None:
        if self._montando:
            return
        self.lo = {"ship": self.nave.currentText(), "lasers": [
            {"head": c.currentText(), "modules": [m.currentData() for m in ms if m.isEnabled() and m.currentData()]}
            for c, ms in self._linhas
        ]}
        self.alterado.emit(copy.deepcopy(self.lo))
