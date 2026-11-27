"""Seção "Comércio" na tela de Configurações."""

from __future__ import annotations

from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QLabel, QSpinBox, QWidget

from beto_hub.core.i18n import tr


class PainelConfigComercio(QWidget):
    def __init__(self, distancia_minima: float, rotas_com_distancia: int, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)

        self.distancia_minima = QDoubleSpinBox()
        self.distancia_minima.setRange(0.1, 50.0)
        self.distancia_minima.setDecimals(1)
        self.distancia_minima.setSingleStep(0.5)
        self.distancia_minima.setSuffix(" Gm")
        self.distancia_minima.setValue(distancia_minima)
        form.addRow(tr("Distância mínima considerada:"), self.distancia_minima)

        self.rotas_com_distancia = QSpinBox()
        self.rotas_com_distancia.setRange(10, 150)
        self.rotas_com_distancia.setSingleStep(10)
        self.rotas_com_distancia.setValue(rotas_com_distancia)
        form.addRow(tr("Rotas analisadas por busca:"), self.rotas_com_distancia)

        ajuda = QLabel(tr(
            "• Distância mínima: rotas mais curtas que isso (ex.: dentro da mesma órbita) contam como "
            "se tivessem essa distância no cálculo da eficiência, porque decolar, pousar e carregar "
            "também levam tempo. Aumente se rotas curtas demais estiverem aparecendo no topo.\n\n"
            "• Rotas analisadas: as N rotas de maior lucro recebem distância, eficiência e risco. "
            "Mais rotas = resultado mais completo, mas a primeira busca demora um pouco mais "
            "(as distâncias ficam guardadas por 12 h)."
        ))
        ajuda.setWordWrap(True)
        ajuda.setProperty("papel", "ajuda")
        form.addRow(ajuda)
