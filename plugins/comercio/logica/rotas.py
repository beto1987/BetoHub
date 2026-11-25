"""Cálculo das rotas de comércio (A -> B, uma mercadoria).

Para cada mercadoria, cruza todo terminal que VENDE para você (preço de
compra) com todo terminal que COMPRA de você (preço de venda) mais caro.
A quantidade da viagem é o menor entre:
  - a carga da nave (SCU),
  - quanto o seu capital compra,
  - o estoque disponível na origem (quando a UEX informa).

Limitação conhecida: a UEX não informa com segurança quanto o destino ainda
aceita comprar; terminais lotados podem pagar menos ou recusar a carga.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

from .modelos import ParametrosBusca, Preco, Rota, Terminal
from .risco import avaliar_risco


def calcular_rotas(
    precos: Iterable[Preco],
    terminais: dict[int, Terminal],
    params: ParametrosBusca,
    limite: int = 300,
) -> list[Rota]:
    """Devolve as rotas viáveis, da mais lucrativa para a menos (sem distância ainda)."""
    if params.scu <= 0 or params.capital <= 0:
        return []

    def terminal_ok(t: Terminal | None) -> bool:
        if t is None or not t.disponivel:
            return False
        if params.ignorar_jogadores and t.eh_jogador:
            return False
        return True

    compras: dict[int, list[tuple[Preco, Terminal]]] = defaultdict(list)
    vendas: dict[int, list[tuple[Preco, Terminal]]] = defaultdict(list)
    for p in precos:
        t = terminais.get(p.id_terminal)
        if not terminal_ok(t):
            continue
        if p.compra and p.compra > 0:
            if params.id_origem and t.id != params.id_origem:
                pass  # só compra na origem escolhida
            elif not params.sistema or t.sistema == params.sistema:
                compras[p.id_mercadoria].append((p, t))
        if p.venda and p.venda > 0:
            if not params.sistema or t.sistema == params.sistema or params.entre_sistemas:
                vendas[p.id_mercadoria].append((p, t))

    rotas: list[Rota] = []
    for id_merc, ofertas in compras.items():
        for pc, origem in ofertas:
            for pv, destino in vendas.get(id_merc, ()):
                if destino.id == origem.id or pv.venda <= pc.compra:
                    continue
                if origem.sistema != destino.sistema and not params.entre_sistemas:
                    continue

                limites = {"nave": params.scu, "capital": math.floor(params.capital / pc.compra)}
                if pc.estoque_compra is not None:
                    limites["estoque"] = math.floor(pc.estoque_compra)
                motivo, scu = min(limites.items(), key=lambda kv: kv[1])
                if scu <= 0:
                    continue

                rotas.append(Rota(
                    id_mercadoria=id_merc, mercadoria=pc.mercadoria or pv.mercadoria,
                    origem=origem, destino=destino,
                    preco_compra=pc.compra, preco_venda=pv.venda,
                    scu=int(scu), limitado_por=motivo,
                    atualizado_origem=pc.atualizado_em, atualizado_destino=pv.atualizado_em,
                ))

    rotas.sort(key=lambda r: r.lucro, reverse=True)
    return rotas[:limite]


def aplicar_distancias(
    rotas: list[Rota],
    distancias: dict[tuple[int, int], float | None],
    distancia_minima: float = 1.0,
    agora: float | None = None,
) -> list[Rota]:
    """Preenche distância, eficiência (lucro/Gm) e risco de cada rota.

    `distancia_minima` evita que rotas dentro da mesma órbita (quase 0 Gm)
    pareçam infinitamente eficientes: decolar, pousar e carregar levam tempo.
    """
    piso = max(0.01, float(distancia_minima))
    for r in rotas:
        r.distancia = distancias.get((r.origem.id, r.destino.id))
        r.eficiencia = r.lucro / max(r.distancia, piso) if r.distancia is not None else None
        r.risco, r.nivel_risco, r.motivos_risco = avaliar_risco(r, agora)
    return rotas


# Chaves de ordenação disponíveis na interface: (rótulo, função, decrescente?)
ORDENACOES = {
    "eficiencia": ("Mais eficientes (lucro por Gm)", lambda r: (r.eficiencia is not None, r.eficiencia or 0), True),
    "lucro": ("Maior lucro", lambda r: r.lucro, True),
    "risco_menor": ("Menor risco", lambda r: (r.risco, -r.lucro), False),
    "risco_maior": ("Maior risco", lambda r: (r.risco, r.lucro), True),
    "distancia": ("Menor distância", lambda r: (r.distancia is None, r.distancia or 0), False),
}


def ordenar(rotas: list[Rota], chave: str) -> list[Rota]:
    _, funcao, decrescente = ORDENACOES.get(chave, ORDENACOES["eficiencia"])
    return sorted(rotas, key=funcao, reverse=decrescente)
