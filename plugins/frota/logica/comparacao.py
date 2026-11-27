"""Atributos mostrados na ficha e no comparador, com formatação e "qual é o melhor". Sem Qt."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


from beto_hub.core import i18n
from beto_hub.core.i18n import N_, tr
from .naves import FichaNave

# Sentido: +1 maior é melhor, -1 menor é melhor, 0 não se compara
MAIOR, MENOR, NEUTRO = 1, -1, 0


def numero(v: float | None, casas: int = 0) -> str:
    """No padrão do idioma: 12345.6 -> "12.345,6" (pt) / "12,345.6" (en)."""
    if v is None:
        return "—"
    return i18n.numero(v, casas)


def tempo_min(v: float | None) -> str:
    if v is None:
        return "—"
    minutos, segundos = int(v), round((v - int(v)) * 60)
    return f"{minutos} min" + (f" {segundos:02d} s" if segundos else "")


@dataclass(frozen=True)
class Atributo:
    grupo: str
    rotulo: str
    valor: Callable[[FichaNave], float | None]
    texto: Callable[[FichaNave], str]
    sentido: int = MAIOR
    dica: str = ""


def _a(grupo, rotulo, valor, unidade="", casas=0, sentido=MAIOR, dica="", escala=1.0) -> Atributo:
    def txt(f: FichaNave) -> str:
        v = valor(f)
        if not v:  # None ou 0 (ex.: caça sem carga, nave sem torretas)
            return "—"
        return f"{numero(v / escala, casas)}{(' ' + unidade) if unidade else ''}"
    return Atributo(grupo, rotulo, valor, txt, sentido, dica)


ATRIBUTOS: list[Atributo] = [
    Atributo(N_("Geral"), N_("Fabricante"), lambda f: None, lambda f: f.fabricante or "—", NEUTRO),
    Atributo(N_("Geral"), N_("Carreira / função"), lambda f: None,
             lambda f: " · ".join(t for t in (f.carreira_pt, f.funcao) if t) or "—", NEUTRO),
    Atributo(N_("Geral"), N_("Tamanho"), lambda f: None, lambda f: f.tamanho_pt or "—", NEUTRO),
    Atributo(N_("Geral"), N_("Tripulação"), lambda f: f.tripulacao_max,
             lambda f: "—" if f.tripulacao_max is None else (
                 str(f.tripulacao_max) if f.tripulacao_min in (None, f.tripulacao_max)
                 else f"{f.tripulacao_min}–{f.tripulacao_max}"), NEUTRO),
    _a(N_("Geral"), N_("Carga"), lambda f: f.carga_scu, "SCU"),
    _a(N_("Geral"), N_("Minério"), lambda f: f.minerio_scu, "SCU", dica=N_("Capacidade das caixas de minério (naves de mineração).")),

    _a(N_("Combate"), N_("DPS total"), lambda f: f.dps_total, dica=N_("Piloto + torretas, com o loadout de fábrica.")),
    _a(N_("Combate"), N_("DPS do piloto"), lambda f: f.dps_piloto),
    _a(N_("Combate"), N_("DPS sustentado (piloto)"), lambda f: f.dps_piloto_sustentado,
       dica=N_("DPS considerando superaquecimento e recarga das armas.")),
    _a(N_("Combate"), N_("Alpha (piloto)"), lambda f: f.alpha_piloto, casas=1, dica=N_("Dano de uma rajada de todas as armas do piloto.")),
    _a(N_("Combate"), N_("DPS das torretas"), lambda f: f.dps_torretas),
    _a(N_("Combate"), N_("Mísseis"), lambda f: f.misseis),
    _a(N_("Combate"), N_("Dano dos mísseis"), lambda f: f.dano_misseis),

    _a(N_("Defesa"), N_("Escudo"), lambda f: f.escudo_hp, "HP"),
    _a(N_("Defesa"), N_("Regeneração do escudo"), lambda f: f.escudo_regen, "HP/s"),
    _a(N_("Defesa"), N_("Casco"), lambda f: f.casco_hp, "HP"),
    _a(N_("Defesa"), N_("Armadura"), lambda f: f.armadura_hp, "HP"),
    _a(N_("Defesa"), N_("Casco + escudo"), lambda f: f.hp_total, "HP", dica=N_("Aproximação de quanto dano a nave aguenta.")),

    _a(N_("Voo"), N_("Velocidade SCM"), lambda f: f.velocidade_scm, "m/s"),
    _a(N_("Voo"), N_("Velocidade máxima"), lambda f: f.velocidade_max, "m/s"),
    _a(N_("Voo"), N_("Boost"), lambda f: f.boost, "m/s"),
    _a(N_("Voo"), N_("Pitch / Yaw / Roll"), lambda f: f.pitch,
       "°/s", sentido=MAIOR, dica=N_("Rotação em graus por segundo (pitch mostrado na comparação).")),
    _a(N_("Quantum"), N_("Velocidade quantum"), lambda f: f.quantum_velocidade, "km/s", escala=1000),
    _a(N_("Quantum"), N_("Alcance quantum"), lambda f: f.quantum_alcance, "Gm", casas=1, escala=1e9),
    _a(N_("Quantum"), N_("Spool"), lambda f: f.quantum_spool, "s", casas=1, sentido=MENOR,
       dica=N_("Tempo para carregar o salto quântico.")),

    Atributo(N_("Seguro e preço"), N_("Resgate do seguro"), lambda f: f.seguro_min, lambda f: tempo_min(f.seguro_min), MENOR),
    Atributo(N_("Seguro e preço"), N_("Resgate expresso"), lambda f: f.seguro_expresso_min,
             lambda f: "—" if f.seguro_expresso_min is None else
             f"{tempo_min(f.seguro_expresso_min)} · {numero(f.seguro_expresso_custo)} aUEC", MENOR),
    Atributo(N_("Seguro e preço"), N_("Preço no jogo"), lambda f: f.preco_jogo,
             lambda f: "—" if f.preco_jogo is None else f"{numero(f.preco_jogo)} aUEC", MENOR,
             N_("Menor preço de compra reportado na UEX.")),
    Atributo(N_("Seguro e preço"), N_("Onde comprar"), lambda f: None, lambda f: f.preco_jogo_local or "—", NEUTRO),
    Atributo(N_("Seguro e preço"), N_("Aluguel"), lambda f: f.aluguel,
             lambda f: "—" if f.aluguel is None else f"{numero(f.aluguel)} aUEC · {f.aluguel_local}", MENOR),
    Atributo(N_("Seguro e preço"), N_("Pledge"), lambda f: f.preco_dolar,
             lambda f: "—" if f.preco_dolar is None else f"US$ {numero(f.preco_dolar)}", NEUTRO),
]

# Na ficha, pitch/yaw/roll aparecem juntos
TEXTO_FICHA: dict[str, Callable[[FichaNave], str]] = {
    N_("Pitch / Yaw / Roll"): lambda f: "—" if f.pitch is None else
    f"{numero(f.pitch)} / {numero(f.yaw)} / {numero(f.roll)} °/s",
}


def melhores(fichas: list[FichaNave], atributo: Atributo) -> set[int]:
    """Índices das naves com o melhor valor no atributo (vazio se não dá para comparar)."""
    if atributo.sentido == NEUTRO or len(fichas) < 2:
        return set()
    valores = [(i, atributo.valor(f)) for i, f in enumerate(fichas)]
    validos = [(i, v) for i, v in valores if v is not None and v > 0]
    if len(validos) < 2:
        return set()
    alvo = (max if atributo.sentido == MAIOR else min)(v for _, v in validos)
    if all(v == alvo for _, v in validos):
        return set()  # empate geral: nada a destacar
    return {i for i, v in validos if v == alvo}
