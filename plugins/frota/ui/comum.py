"""Peças de interface usadas pelas telas da Frota."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QCompleter

from ..logica.naves import FichaNave

COR_OK = "#4cd98a"
COR_ACENTO = "#35c8f5"
COR_SUAVE = "#7f98ad"


def combo_pesquisavel(combo: QComboBox) -> None:
    """Permite digitar para filtrar (ex.: "cut" encontra "Cutlass Black")."""
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    completer = combo.completer()
    completer.setFilterMode(Qt.MatchContains)
    completer.setCompletionMode(QCompleter.PopupCompletion)
    completer.setCaseSensitivity(Qt.CaseInsensitive)


def preencher_naves(combo: QComboBox, fichas: list[FichaNave], vazio: str | None = None,
                    manter_uuid: str = "") -> None:
    """Lista as naves (dado = uuid). `vazio` adiciona uma primeira opção sem nave."""
    combo.blockSignals(True)
    combo.clear()
    if vazio is not None:
        combo.addItem(vazio, "")
    for f in fichas:
        combo.addItem(f"{f.nome}  ·  {f.carreira_pt or '—'}", f.uuid)
    combo.setCurrentIndex(max(0, combo.findData(manter_uuid)) if manter_uuid else 0)
    combo.blockSignals(False)
