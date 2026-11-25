"""Estimativas de rendimento, custo, tempo e lucro por método de refino.

Fontes (UEX Corp):
- refineries_methods ... nome e notas 1–3 de rendimento/custo/velocidade de cada método
- refineries_audits .... pedidos reais enviados pela comunidade (quantidade, refinado, custo, minutos)
- refineries_yields ..... bônus de rendimento (%) de cada refinaria por minério
- commodities_prices_all  melhor preço de venda do minério refinado

Como estimamos (para cada método e cada minério do pedido):
1. Separa as auditorias do mesmo método, na ordem de preferência:
   mesma refinaria e minério -> mesmo minério -> qualquer minério.
   Usa o primeiro grupo com pelo menos AMOSTRAS_MINIMAS pedidos.
2. Tira o bônus da refinaria onde cada auditoria foi feita, para obter o
   rendimento "base" do método; depois aplica o bônus da SUA refinaria.
3. Usa a MEDIANA (resiste melhor a relatos errados) de: rendimento,
   custo por cSCU e minutos por cSCU.

São estimativas: confirme custo e tempo no terminal do jogo ao criar o pedido.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

AMOSTRAS_MINIMAS = 3
CSCU_POR_SCU = 100

NIVEIS = ("refinaria", "minério", "geral")  # do mais específico para o mais genérico
NOMES_NIVEL = {"refinaria": "desta refinaria", "minério": "deste minério em outras refinarias",
               "geral": "deste método com outros minérios", "sem dados": "sem dados"}


# ---------------------------------------------------------------- nomes de minério
def eh_bruto(nome: str) -> bool:
    return bool(re.search(r"\((raw|ore)\)|\b(raw|ore)\b", nome or "", re.I))


def chave_minerio(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    sem_sufixo = re.sub(r"\((raw|ore)\)|\b(raw|ore)\b", "", sem_acento, flags=re.I)
    return re.sub(r"[^a-z]", "", sem_sufixo.lower())


def nome_limpo(nome: str) -> str:
    return re.sub(r"\s*\((raw|ore)\)\s*$", "", nome or "", flags=re.I).strip()


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- dados
@dataclass(frozen=True)
class Metodo:
    id: int
    nome: str
    codigo: str
    nota_rendimento: int  # 1 baixo · 2 médio · 3 alto
    nota_custo: int       # 1 baixo · 2 médio · 3 alto
    nota_velocidade: int  # 1 lento · 2 médio · 3 rápido

    @classmethod
    def de_uex(cls, d: dict[str, Any]) -> "Metodo":
        return cls(int(d.get("id") or 0), str(d.get("name") or "?"), str(d.get("code") or ""),
                   int(d.get("rating_yield") or 0), int(d.get("rating_cost") or 0), int(d.get("rating_speed") or 0))


@dataclass(frozen=True)
class Auditoria:
    id_terminal: int
    chave: str
    metodo: int
    quantidade: float
    refinado: float
    custo: float
    minutos: float
    bonus: float

    @classmethod
    def de_uex(cls, d: dict[str, Any]) -> "Auditoria | None":
        q, r = _num(d.get("quantity")), _num(d.get("quantity_yield"))
        if not q or q <= 0 or r is None or r < 0:
            return None
        return cls(int(d.get("id_terminal") or 0), chave_minerio(str(d.get("commodity_name") or "")),
                   int(d.get("method") or 0), q, r, _num(d.get("total_cost")) or 0.0,
                   _num(d.get("total_time")) or 0.0, _num(d.get("yield")) or 0.0)


@dataclass
class Refinaria:
    id_terminal: int
    nome: str
    sistema: str
    bonus: dict[str, float] = field(default_factory=dict)  # chave do minério -> %

    @property
    def rotulo(self) -> str:
        return f"{self.nome} ({self.sistema})" if self.sistema and self.sistema not in self.nome else self.nome


def refinarias_de_uex(linhas: Iterable[dict[str, Any]]) -> dict[int, Refinaria]:
    saida: dict[int, Refinaria] = {}
    for l in linhas or []:
        tid = int(l.get("id_terminal") or 0)
        if not tid:
            continue
        r = saida.setdefault(tid, Refinaria(tid, str(l.get("terminal_name") or "?"), str(l.get("star_system_name") or "")))
        valor = _num(l.get("value"))
        if valor is not None:
            r.bonus[chave_minerio(str(l.get("commodity_name") or ""))] = valor
    return saida


def minerios_de_uex(linhas: Iterable[dict[str, Any]]) -> dict[str, str]:
    """chave -> nome para exibir (sem "(Raw)")."""
    saida: dict[str, str] = {}
    for l in linhas or []:
        nome = str(l.get("commodity_name") or "")
        chave = chave_minerio(nome)
        if chave and chave not in saida:
            saida[chave] = nome_limpo(nome)
    return dict(sorted(saida.items(), key=lambda kv: kv[1].lower()))


def precos_refinados(precos: Iterable[dict[str, Any]]) -> dict[str, tuple[float, str]]:
    """Melhor preço de venda (aUEC/SCU) de cada minério REFINADO e onde vender."""
    melhor: dict[str, tuple[float, str]] = {}
    for p in precos or []:
        nome = str(p.get("commodity_name") or "")
        venda = _num(p.get("price_sell"))
        if not venda or venda <= 0 or eh_bruto(nome):
            continue
        chave = chave_minerio(nome)
        if chave and (chave not in melhor or venda > melhor[chave][0]):
            melhor[chave] = (venda, str(p.get("terminal_name") or ""))
    return melhor


def detectar_unidade(auditorias: list[Auditoria]) -> int:
    """Quantos cSCU vale 1 unidade das auditorias (1 se já vier em cSCU, 100 se vier em SCU).

    A documentação da UEX diz só "units". Pedidos típicos têm de 10 a 100 SCU
    (1.000 a 10.000 cSCU): se a mediana for alta, os números já estão em cSCU.
    """
    if not auditorias:
        return 1
    return 1 if statistics.median(a.quantidade for a in auditorias) > 400 else CSCU_POR_SCU


# ---------------------------------------------------------------- estimativa
@dataclass
class Item:
    chave: str
    nome: str
    quantidade_cscu: float


@dataclass
class EstimativaItem:
    item: Item
    refinado_scu: float | None
    custo: float | None
    minutos: float | None
    valor: float | None
    amostras: int
    nivel: str


@dataclass
class Estimativa:
    metodo: Metodo
    itens: list[EstimativaItem]

    def _soma(self, campo: str) -> float | None:
        valores = [getattr(i, campo) for i in self.itens]
        return None if any(v is None for v in valores) else sum(valores)

    @property
    def refinado_scu(self) -> float | None:
        return self._soma("refinado_scu")

    @property
    def custo(self) -> float | None:
        return self._soma("custo")

    @property
    def minutos(self) -> float | None:
        return self._soma("minutos")

    @property
    def valor(self) -> float | None:
        return self._soma("valor")

    @property
    def lucro(self) -> float | None:
        return None if self.valor is None or self.custo is None else self.valor - self.custo

    @property
    def amostras(self) -> int:
        return min((i.amostras for i in self.itens), default=0)

    @property
    def nivel(self) -> str:
        ordem = {n: k for k, n in enumerate((*NIVEIS, "sem dados"))}
        return max((i.nivel for i in self.itens), key=lambda n: ordem[n], default="sem dados")


class Estimador:
    def __init__(self, metodos: list[Metodo], auditorias: list[Auditoria], refinarias: dict[int, Refinaria],
                 precos: dict[str, tuple[float, str]], cscu_por_unidade: int | None = None):
        self.metodos = metodos
        self.auditorias = auditorias
        self.refinarias = refinarias
        self.precos = precos
        self.fator = cscu_por_unidade or detectar_unidade(auditorias)

    def _amostras(self, metodo: int, id_terminal: int, chave: str) -> tuple[list[Auditoria], str]:
        do_metodo = [a for a in self.auditorias if a.metodo == metodo]
        grupos = (
            ("refinaria", [a for a in do_metodo if a.chave == chave and a.id_terminal == id_terminal]),
            ("minério", [a for a in do_metodo if a.chave == chave]),
            ("geral", do_metodo),
        )
        for nivel, grupo in grupos:
            if len(grupo) >= AMOSTRAS_MINIMAS:
                return grupo, nivel
        return [], "sem dados"

    def _estimar_item(self, metodo: Metodo, id_terminal: int, item: Item) -> EstimativaItem:
        grupo, nivel = self._amostras(metodo.id, id_terminal, item.chave)
        if not grupo or item.quantidade_cscu <= 0:
            return EstimativaItem(item, None, None, None, None, len(grupo), "sem dados")
        # rendimento base do método (sem o bônus da refinaria de cada relato)
        base = statistics.median((a.refinado / a.quantidade) / (1 + a.bonus / 100) for a in grupo)
        custo_cscu = statistics.median(a.custo / (a.quantidade * self.fator) for a in grupo)
        min_cscu = statistics.median(a.minutos / (a.quantidade * self.fator) for a in grupo)

        refinaria = self.refinarias.get(id_terminal)
        bonus = refinaria.bonus.get(item.chave, 0.0) if refinaria else 0.0
        refinado_scu = item.quantidade_cscu * base * (1 + bonus / 100) / CSCU_POR_SCU
        preco = self.precos.get(item.chave)
        return EstimativaItem(
            item=item,
            refinado_scu=refinado_scu,
            custo=item.quantidade_cscu * custo_cscu,
            minutos=item.quantidade_cscu * min_cscu,
            valor=refinado_scu * preco[0] if preco else None,
            amostras=len(grupo),
            nivel=nivel,
        )

    def estimar(self, id_terminal: int, itens: list[Item]) -> list[Estimativa]:
        """Uma estimativa por método, do maior lucro para o menor (sem dados por último)."""
        saida = [Estimativa(m, [self._estimar_item(m, id_terminal, i) for i in itens]) for m in self.metodos]
        saida.sort(key=lambda e: (e.lucro is None, -(e.lucro or 0), e.metodo.nome))
        return saida


# ---------------------------------------------------------------- formatação
def formatar_minutos(minutos: float | None) -> str:
    if minutos is None:
        return "—"
    total = int(round(minutos))
    h, m = divmod(total, 60)
    if h >= 24:
        d, h = divmod(h, 24)
        return f"{d} d {h} h"
    return f"{h} h {m:02d} min" if h else f"{m} min"
