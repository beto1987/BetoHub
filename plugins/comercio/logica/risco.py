"""Nota de risco de uma rota (0 a 100) com os motivos.

A UEX não informa jurisdição, armistício nem segurança. A nota é uma
estimativa com os dados disponíveis; os pesos estão aqui em cima para
facilitar ajustes.
"""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .modelos import Rota

# ---- pesos (pontos máximos de cada critério) ----
PESO_VALOR = 25          # valor da carga em jogo
VALOR_BASE = 50_000      # abaixo disso, 0 pontos
VALOR_TETO = 5_000_000   # a partir disso, pontuação máxima
PESO_PYRO = 25           # sistema sem lei
PESO_OUTRO_SISTEMA = 15  # outros sistemas fora de Stanton (ex.: Nyx)
PESO_ENTRE_SISTEMAS = 10 # viagem atravessa um ponto de salto
PESO_NQA = 15            # terminal "no questions asked"
PESO_JOGADOR = 10        # terminal de jogador
PESO_OUTPOST = 6         # por ponta da rota em outpost (máx. 2 pontas)
PESO_DISTANCIA = 10      # 1 ponto a cada 5 Gm
PESO_DADOS_ANTIGOS = (   # (horas, pontos): preço reportado há muito tempo
    (72, 20), (24, 12), (6, 5),
)

NIVEIS = ((60, "alto"), (30, "médio"), (0, "baixo"))
SISTEMA_SEGURO = "Stanton"
SISTEMA_SEM_LEI = "Pyro"


def nivel_da_nota(nota: int) -> str:
    for minimo, nome in NIVEIS:
        if nota >= minimo:
            return nome
    return "baixo"


def avaliar_risco(rota: "Rota", agora: float | None = None) -> tuple[int, str, list[str]]:
    agora = agora or time.time()
    pontos = 0.0
    motivos: list[str] = []

    def somar(valor: float, motivo: str) -> None:
        nonlocal pontos
        if valor > 0:
            pontos += valor
            motivos.append(f"+{round(valor)} {motivo}")

    # 1) valor da carga (escala logarítmica entre VALOR_BASE e VALOR_TETO)
    inv = rota.investimento
    if inv > VALOR_BASE:
        fracao = math.log10(inv / VALOR_BASE) / math.log10(VALOR_TETO / VALOR_BASE)
        somar(PESO_VALOR * min(1.0, fracao), f"carga de {inv:,.0f} aUEC".replace(",", "."))

    # 2) sistemas
    sistemas = {rota.origem.sistema, rota.destino.sistema} - {""}
    if SISTEMA_SEM_LEI in sistemas:
        somar(PESO_PYRO, "passa por Pyro (sem lei)")
    elif sistemas - {SISTEMA_SEGURO}:
        somar(PESO_OUTRO_SISTEMA, f"fora de Stanton ({', '.join(sorted(sistemas - {SISTEMA_SEGURO}))})")
    if rota.entre_sistemas:
        somar(PESO_ENTRE_SISTEMAS, "atravessa ponto de salto")

    # 3) tipo de terminal
    if rota.origem.eh_nqa or rota.destino.eh_nqa:
        somar(PESO_NQA, "terminal \"sem perguntas\" (NQA)")
    if rota.origem.eh_jogador or rota.destino.eh_jogador:
        somar(PESO_JOGADOR, "terminal de jogador")
    outposts = sum(t.eh_outpost for t in (rota.origem, rota.destino))
    somar(PESO_OUTPOST * outposts, "parada em outpost" if outposts == 1 else "origem e destino em outposts")

    # 4) distância (tempo exposto)
    if rota.distancia:
        somar(min(PESO_DISTANCIA, rota.distancia / 5), f"{rota.distancia:.1f} Gm de viagem")

    # 5) idade dos preços (o preço pode ter mudado)
    reportes = [t for t in (rota.atualizado_origem, rota.atualizado_destino) if t]
    if reportes:
        horas = (agora - min(reportes)) / 3600
        for limite_h, valor in PESO_DADOS_ANTIGOS:
            if horas >= limite_h:
                somar(valor, f"preço reportado há {horas:.0f} h")
                break

    nota = int(round(min(100.0, pontos)))
    return nota, nivel_da_nota(nota), motivos or ["nenhum fator de risco relevante"]
