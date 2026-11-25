"""Painéis genéricos: módulo em construção e módulo com erro."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget


def _rotulo(texto: str, papel: str | None = None, quebra: bool = True) -> QLabel:
    rotulo = QLabel(texto)
    rotulo.setWordWrap(quebra)
    if papel:
        rotulo.setProperty("papel", papel)
    return rotulo


class PainelEmConstrucao(QWidget):
    """Placeholder bonito para módulos que ainda serão desenvolvidos."""

    def __init__(self, titulo: str, descricao: str, etapa: str = "", compacto: bool = False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12) if compacto else layout.setContentsMargins(40, 40, 40, 40)
        layout.addStretch(1)
        layout.addWidget(_rotulo(titulo.upper(), "titulo"), alignment=Qt.AlignHCenter)
        corpo = _rotulo(descricao)
        corpo.setAlignment(Qt.AlignHCenter)
        layout.addWidget(corpo)
        if etapa:
            aviso = _rotulo(f"◈ {etapa}", "alerta")
            aviso.setAlignment(Qt.AlignHCenter)
            layout.addWidget(aviso)
        layout.addStretch(2)


class PainelErroPlugin(QWidget):
    """Mostrado no lugar da aba de um módulo que falhou ao carregar."""

    def __init__(self, nome: str, erro: str, detalhe: str, pasta_logs: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(_rotulo(f"O MÓDULO {nome.upper()} NÃO CARREGOU", "erro"))
        layout.addWidget(_rotulo(
            "O restante do Hub continua funcionando. "
            f"Detalhes completos no log em:\n{pasta_logs}", "ajuda"
        ))
        layout.addWidget(_rotulo(erro))
        if detalhe:
            texto = QPlainTextEdit(detalhe)
            texto.setReadOnly(True)
            layout.addWidget(texto, 1)
        else:
            layout.addStretch(1)
