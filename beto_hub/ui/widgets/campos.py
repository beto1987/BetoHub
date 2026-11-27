"""Textos de dica discretos em todos os campos do Hub (um filtro de eventos instalado no app).

Ao clicar num campo para preencher, a dica some; se você sair sem digitar, ela volta:
- placeholders (QLineEdit, QPlainTextEdit, QTextEdit): somem enquanto o campo tem foco;
- listas com busca cuja opção "vazia" é um texto de dica ("— nenhuma —", "— escolha o local —"):
  o texto some ao clicar e volta se você sair sem escolher nada;
- números com texto especial ("não informada") ou com valor zero: o conteúdo fica
  selecionado, então o que você digita substitui em vez de somar ("0" não precisa ser apagado).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QComboBox, QLineEdit, QPlainTextEdit, QTextEdit

_DICA = "_betohub_dica_guardada"
_VAZIO = "_betohub_indice_vazio"
_PREFIXOS_DICA = ("—", "(")  # opções como "— nenhuma —" e "(nenhum)"


def _eh_opcao_vazia(combo: QComboBox, indice: int) -> bool:
    if indice < 0:
        return False
    dado = combo.itemData(indice)
    return dado in (None, "", 0) and combo.itemText(indice).strip().startswith(_PREFIXOS_DICA)


def _esconder_placeholder(w) -> None:
    dica = w.placeholderText()
    if dica and w.property(_DICA) is None:
        w.setProperty(_DICA, dica)
        w.setPlaceholderText("")


def _mostrar_placeholder(w) -> None:
    dica = w.property(_DICA)
    if dica is not None:
        w.setPlaceholderText(dica)
        w.setProperty(_DICA, None)


def _campo_do_spin(spin: QAbstractSpinBox) -> QLineEdit | None:
    return spin.findChild(QLineEdit)


class FiltroDicas(QObject):
    """Instale com `instalar_dicas_discretas(app)`."""

    def eventFilter(self, obj, evento):  # noqa: N802 (nome exigido pelo Qt)
        tipo = evento.type()
        if tipo not in (QEvent.FocusIn, QEvent.FocusOut):
            return False
        entrando = tipo == QEvent.FocusIn
        try:
            if isinstance(obj, QComboBox):
                self._combo(obj, entrando)
            elif isinstance(obj, QAbstractSpinBox):
                self._spin(obj, entrando)
            elif isinstance(obj, QLineEdit):
                pai = obj.parentWidget()
                if isinstance(pai, QComboBox):
                    self._combo(pai, entrando)
                elif isinstance(pai, QAbstractSpinBox):
                    self._spin(pai, entrando)
                else:
                    (_esconder_placeholder if entrando else _mostrar_placeholder)(obj)
            elif isinstance(obj, (QPlainTextEdit, QTextEdit)):
                (_esconder_placeholder if entrando else _mostrar_placeholder)(obj)
        except RuntimeError:
            pass  # widget sendo destruído
        return False  # nunca bloqueia o evento: o campo continua funcionando normalmente

    # ------------------------------------------------------------ listas com busca
    @staticmethod
    def _combo(combo: QComboBox, entrando: bool) -> None:
        campo = combo.lineEdit()
        if not combo.isEditable() or campo is None:
            return
        if entrando:
            _esconder_placeholder(campo)
            if _eh_opcao_vazia(combo, combo.currentIndex()) and combo.property(_VAZIO) is None:
                combo.setProperty(_VAZIO, combo.currentIndex())
                campo.clear()
            return
        indice = combo.property(_VAZIO)
        combo.setProperty(_VAZIO, None)

        def restaurar() -> None:
            try:
                if indice is not None and not campo.text().strip():
                    combo.blockSignals(True)
                    combo.setCurrentIndex(indice)
                    combo.blockSignals(False)
                    combo.setEditText(combo.itemText(indice))
                _mostrar_placeholder(campo)
            except RuntimeError:
                pass

        QTimer.singleShot(0, restaurar)  # depois do tratamento normal do Qt

    # ------------------------------------------------------------ números
    @staticmethod
    def _spin(spin: QAbstractSpinBox, entrando: bool) -> None:
        campo = _campo_do_spin(spin)
        if campo is None or spin.isReadOnly():
            return
        especial = spin.specialValueText()
        no_minimo = getattr(spin, "value", None) and getattr(spin, "minimum", None) and spin.value() == spin.minimum()
        if entrando:
            if especial and no_minimo:
                # "não informada": some ao clicar (é dica, não valor)
                spin.setProperty(_VAZIO, True)
                QTimer.singleShot(0, lambda: campo.clear() if spin.hasFocus() else None)
            else:
                # Seleciona tudo: digitar substitui o "0" em vez de somar ao texto
                QTimer.singleShot(0, lambda: spin.selectAll() if spin.hasFocus() else None)
            return
        if not spin.property(_VAZIO):
            return
        spin.setProperty(_VAZIO, None)

        def restaurar() -> None:
            try:
                if spin.value() == spin.minimum():
                    spin.setValue(spin.minimum())
                    campo.setText(spin.specialValueText())  # a dica volta
            except RuntimeError:
                pass

        QTimer.singleShot(0, restaurar)


def instalar_dicas_discretas(app: QApplication) -> FiltroDicas:
    filtro = FiltroDicas(app)
    app.installEventFilter(filtro)
    return filtro
