"""Painel de detalhes de um contrato: objetivos, recompensa, notas e ações."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
    QWidget,
)

from beto_hub.core.i18n import tr
from ..logica.eventos import ABANDONADO, CONCLUIDO, NOMES_STATUS
from ..logica.repositorio import OBJ_CANCELADO, OBJ_FEITO, Contrato
from .comum import COR_SUAVE, COR_TEXTO, CORES_STATUS, data_hora, duracao

if TYPE_CHECKING:
    from ..controlador import ControladorContratos

SIMBOLOS = {OBJ_FEITO: ("✔", "#4cd98a"), OBJ_CANCELADO: ("✕", COR_SUAVE)}


def html_objetivos(c: Contrato, limite: int = 12) -> str:
    if not c.objetivos:
        return f"<span style='color:{COR_SUAVE}'>{tr('O log não trouxe objetivos para este contrato.')}</span>"
    linhas = []
    for o in c.objetivos[:limite]:
        simbolo, cor = SIMBOLOS.get(o.status, ("○", COR_TEXTO))
        estilo = "text-decoration: line-through;" if o.status == OBJ_CANCELADO else ""
        linhas.append(f"<div style='color:{cor}; {estilo}'>{simbolo} {html.escape(o.texto or o.id)}</div>")
    if len(c.objetivos) > limite:
        linhas.append(f"<div style='color:{COR_SUAVE}'>{tr('… mais {n}', n=len(c.objetivos) - limite)}</div>")
    return "".join(linhas)


class DetalheContrato(QWidget):
    def __init__(self, c: "ControladorContratos", parent=None):
        super().__init__(parent)
        self.c = c
        self.contrato: Contrato | None = None
        self._missao_mostrada = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 0, 0)
        self.titulo = QLabel()
        self.titulo.setProperty("papel", "titulo")
        self.titulo.setWordWrap(True)
        layout.addWidget(self.titulo)
        self.info = QLabel()
        self.info.setTextFormat(Qt.RichText)
        self.info.setWordWrap(True)
        layout.addWidget(self.info)

        rotulo = QLabel(tr("OBJETIVOS"))
        rotulo.setProperty("papel", "ajuda")
        layout.addWidget(rotulo)
        self.objetivos = QLabel()
        self.objetivos.setTextFormat(Qt.RichText)
        self.objetivos.setWordWrap(True)
        self.objetivos.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.objetivos)

        form = QFormLayout()
        self.recompensa = QDoubleSpinBox()
        self.recompensa.setRange(0, 1e9)
        self.recompensa.setDecimals(0)
        self.recompensa.setGroupSeparatorShown(True)
        self.recompensa.setSuffix(" aUEC")
        self.recompensa.setSpecialValueText(tr("não informada"))
        self.recompensa.setToolTip(tr("O Game.log não mostra a recompensa: informe o valor que aparece no contrato."))
        form.addRow(tr("Recompensa:"), self.recompensa)
        self.notas = QPlainTextEdit()
        self.notas.setPlaceholderText(tr("Anotações sobre o contrato…"))
        self.notas.setFixedHeight(64)
        form.addRow(tr("Notas:"), self.notas)
        layout.addLayout(form)

        botoes = QHBoxLayout()
        self.botao_salvar = QPushButton(tr("Salvar"))
        self.botao_salvar.clicked.connect(self._salvar)
        botoes.addWidget(self.botao_salvar)
        self.botao_log = QPushButton(tr("Registrar no Log do Capitão"))
        self.botao_log.setProperty("destaque", "true")
        self.botao_log.clicked.connect(self._registrar)
        botoes.addWidget(self.botao_log)
        botoes.addStretch(1)
        layout.addLayout(botoes)

        manuais = QHBoxLayout()
        self.botao_concluir = QPushButton(tr("Marcar concluído"))
        self.botao_concluir.setToolTip(tr("Use se o jogo encerrou o contrato sem registrar no log."))
        self.botao_concluir.clicked.connect(lambda: self._encerrar(CONCLUIDO))
        self.botao_abandonar = QPushButton(tr("Marcar abandonado"))
        self.botao_abandonar.clicked.connect(lambda: self._encerrar(ABANDONADO))
        self.botao_excluir = QPushButton(tr("Excluir"))
        self.botao_excluir.setProperty("perigo", "true")
        self.botao_excluir.clicked.connect(self._excluir)
        for b in (self.botao_concluir, self.botao_abandonar):
            manuais.addWidget(b)
        manuais.addStretch(1)
        manuais.addWidget(self.botao_excluir)
        layout.addLayout(manuais)
        layout.addStretch(1)
        self.mostrar(None)

    def mostrar(self, contrato: Contrato | None) -> None:
        self.contrato = contrato
        tem = contrato is not None
        for w in (self.recompensa, self.notas, self.botao_salvar, self.botao_excluir):
            w.setEnabled(tem)
        if not tem:
            self.titulo.setText(tr("CONTRATO"))
            self.info.setText(f"<span style='color:{COR_SUAVE}'>{tr('Selecione um contrato na lista.')}</span>")
            self.objetivos.setText("")
            self.recompensa.setValue(0)
            self.notas.setPlainText("")
            for b in (self.botao_log, self.botao_concluir, self.botao_abandonar):
                b.setVisible(False)
            return

        c = contrato
        self.titulo.setText(c.rotulo.upper())
        cor = CORES_STATUS.get(c.status, COR_TEXTO)
        partes = [f"<b style='color:{cor}'>{tr(NOMES_STATUS.get(c.status, c.status))}</b>", tr(c.tipo) if c.tipo else "—",
                  tr("aceito {quando}", quando=data_hora(c.aceito_em))]
        if not c.ativo:
            partes.append(tr("encerrado {quando}", quando=data_hora(c.encerrado_em)))
        partes.append(tr("duração {tempo}", tempo=duracao(c.duracao_s)))
        if c.reputacao:
            partes.append(html.escape(c.reputacao))
        self.info.setText(f"<span style='color:{COR_SUAVE}'>{' · '.join(partes)}</span>")
        self.objetivos.setText(html_objetivos(c))
        # A lista recarrega quando o log traz novidades: não apaga o que você está digitando
        editando = self.recompensa.hasFocus() or self.recompensa.lineEdit().hasFocus() or self.notas.hasFocus()
        if not (editando and self._missao_mostrada == c.missao):
            self.recompensa.setValue(c.recompensa or 0)
            self.notas.setPlainText(c.notas)
        self._missao_mostrada = c.missao

        self.botao_concluir.setVisible(c.ativo)
        self.botao_abandonar.setVisible(c.ativo)
        self.botao_log.setVisible(c.status == CONCLUIDO)
        self.botao_log.setText(tr("Registrar de novo no Log") if c.registrado_log else tr("Registrar no Log do Capitão"))

    # ------------------------------------------------------------ ações
    def _valores(self) -> tuple[float | None, str]:
        return (self.recompensa.value() or None), self.notas.toPlainText()

    def _salvar(self) -> None:
        if self.contrato:
            self.c.salvar_detalhes(self.contrato, *self._valores())

    def _registrar(self) -> None:
        if not self.contrato:
            return
        self._salvar()
        atualizado = self.c.repo.obter(self.contrato.missao)
        if atualizado:
            self.c.registrar_no_log(atualizado)

    def _encerrar(self, status: str) -> None:
        if self.contrato and QMessageBox.question(
                self, tr("Contratos"), tr("Marcar \"{contrato}\" como {status}?", contrato=self.contrato.rotulo,
                                         status=tr(NOMES_STATUS[status]).lower()),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self._salvar()
            self.c.encerrar_manual(self.contrato, status)

    def _excluir(self) -> None:
        if self.contrato and QMessageBox.question(
                self, tr("Contratos"), tr("Excluir \"{contrato}\"?\nEssa ação não pode ser desfeita.", contrato=self.contrato.rotulo),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.c.excluir(self.contrato)
