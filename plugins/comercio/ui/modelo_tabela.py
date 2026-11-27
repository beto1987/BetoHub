"""Modelo da tabela de rotas (Qt Model/View) com ordenação por qualquer coluna."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from beto_hub.core.i18n import N_, tr
from ..logica.modelos import Rota
from . import formato as fmt

_USER_ROLE = int(getattr(Qt.UserRole, "value", Qt.UserRole))
PAPEL_ORDENACAO = _USER_ROLE + 1  # valor numérico usado para ordenar
PAPEL_ROTA = _USER_ROLE + 2       # objeto Rota da linha

LIMITE = {"nave": N_("limitado pela carga da nave"), "capital": N_("limitado pelo seu capital"),
          "estoque": N_("limitado pelo estoque da origem")}

# (título, texto exibido, valor de ordenação, alinhado à direita?)
Coluna = tuple[str, Callable[[Rota], str], Callable[[Rota], Any], bool]
COLUNAS: list[Coluna] = [
    (N_("Mercadoria"), lambda r: r.mercadoria, lambda r: r.mercadoria.lower(), False),
    (N_("Origem"), lambda r: r.origem.rotulo, lambda r: r.origem.rotulo.lower(), False),
    (N_("Destino"), lambda r: r.destino.rotulo, lambda r: r.destino.rotulo.lower(), False),
    ("SCU", lambda r: fmt.inteiro(r.scu), lambda r: r.scu, True),
    (N_("Investimento"), lambda r: fmt.inteiro(r.investimento), lambda r: r.investimento, True),
    (N_("Lucro"), lambda r: fmt.inteiro(r.lucro), lambda r: r.lucro, True),
    (N_("Margem"), lambda r: f"{fmt.decimal(r.margem_pct)}%", lambda r: r.margem_pct, True),
    (N_("Distância (Gm)"), lambda r: fmt.decimal(r.distancia, 2), lambda r: r.distancia if r.distancia is not None else 1e12, True),
    (N_("Eficiência (aUEC/Gm)"), lambda r: fmt.inteiro(r.eficiencia), lambda r: r.eficiencia if r.eficiencia is not None else -1.0, True),
    (N_("Risco"), lambda r: f"{r.risco} · {tr(r.nivel_risco)}", lambda r: r.risco, True),
]
COL = {titulo: i for i, (titulo, *_resto) in enumerate(COLUNAS)}


class ModeloRotas(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rotas: list[Rota] = []

    def definir_rotas(self, rotas: list[Rota]) -> None:
        self.beginResetModel()
        self._rotas = list(rotas)
        self.endResetModel()

    def rota(self, linha: int) -> Rota | None:
        return self._rotas[linha] if 0 <= linha < len(self._rotas) else None

    # ---- interface do Qt
    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rotas)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(COLUNAS)

    def headerData(self, secao, orientacao, papel=Qt.DisplayRole):  # noqa: N802
        if orientacao == Qt.Horizontal and papel == Qt.DisplayRole:
            return tr(COLUNAS[secao][0])
        if orientacao == Qt.Vertical and papel == Qt.DisplayRole:
            return secao + 1
        return None

    def data(self, indice: QModelIndex, papel=Qt.DisplayRole):
        if not indice.isValid():
            return None
        r = self._rotas[indice.row()]
        titulo, texto, valor, direita = COLUNAS[indice.column()]

        if papel == Qt.DisplayRole:
            return texto(r)
        if papel == PAPEL_ORDENACAO:
            return valor(r)
        if papel == PAPEL_ROTA:
            return r
        if papel == Qt.TextAlignmentRole:
            return (Qt.AlignRight if direita else Qt.AlignLeft) | Qt.AlignVCenter
        if papel == Qt.ForegroundRole:
            if titulo == "Risco":
                return QColor(fmt.CORES_RISCO.get(r.nivel_risco, "#d6e6f2"))
            if titulo == "Lucro":
                return QColor("#4cd98a")
        if papel == Qt.ToolTipRole:
            if titulo == "Origem":
                return tr("{local}\n({tipo}) · compra a {preco} aUEC/SCU", local=r.origem.descricao,
                          tipo=tr(r.origem.tipo_local), preco=fmt.decimal(r.preco_compra, 2))
            if titulo == "Destino":
                return tr("{local}\n({tipo}) · vende a {preco} aUEC/SCU", local=r.destino.descricao,
                          tipo=tr(r.destino.tipo_local), preco=fmt.decimal(r.preco_venda, 2))
            if titulo == "SCU":
                return tr(LIMITE[r.limitado_por]) if r.limitado_por in LIMITE else ""
            if titulo == "Risco":
                return tr("Nota de risco (0–100):") + "\n" + "\n".join(r.motivos_risco)
            if titulo.startswith("Eficiência"):
                return tr("Lucro por gigâmetro percorrido. Quanto maior, mais lucro em menos viagem.")
            if titulo.startswith("Distância") and r.distancia is None:
                return tr("A UEX não informou a distância deste par de terminais.")
        return None
