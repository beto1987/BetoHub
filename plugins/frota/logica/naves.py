"""Fichas das naves a partir da Star Citizen Wiki (loadout de fábrica). Sem Qt, testável.

A lista da Wiki tem entradas que não são naves "compráveis" (maquetes de exposição,
versões de missão) e nomes repetidos (pinturas Best in Show com as mesmas
estatísticas). `fichas_de_wiki` limpa isso e garante um nome único por ficha.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from beto_hub.core.i18n import N_, tr
from beto_hub.core.texto import chave_nome

# Partes do class_name que marcam entradas que não são naves de jogador
_CLASSES_IGNORADAS = re.compile(r"_Display$|_Boarded|_TEMP_", re.I)

CARREIRAS = {
    "combat": N_("Combate"), "transporter": N_("Transporte"), "transport": N_("Transporte"),
    "exploration": N_("Exploração"), "industrial": N_("Industrial"), "competition": N_("Corrida"),
    "multi-role": N_("Multifunção"), "support": N_("Suporte"), "ground": N_("Terrestre"),
    "starter": N_("Iniciante"), "destroyer": N_("Destróier"), "gunship": N_("Canhoneira"),
}
TAMANHOS = {"vehicle": N_("Veículo"), "snub": N_("Mínima"), "small": N_("Pequena"), "medium": N_("Média"),
            "large": N_("Grande"), "capital": N_("Capital")}


def _num(v: Any) -> float | None:
    try:
        return None if v is None or isinstance(v, bool) else float(v)
    except (TypeError, ValueError):
        return None


def _en(v: Any) -> str:
    """Campos traduzidos da Wiki vêm como {"en_EN": ...}; outros já são texto."""
    if isinstance(v, dict):
        return str(v.get("en_EN") or "")
    return str(v or "")


@dataclass(frozen=True)
class Arma:
    nome: str
    dps: float
    quantidade: int = 1


@dataclass
class FichaNave:
    uuid: str
    nome: str
    nome_jogo: str = ""
    fabricante: str = ""
    codigo_fabricante: str = ""
    classe: str = ""                  # class_name (identifica a variante)
    terrestre: bool = False
    tamanho: str = ""
    carreira: str = ""
    funcao: str = ""
    status: str = ""                  # flight-ready, in-concept...
    tripulacao_min: int | None = None
    tripulacao_max: int | None = None
    carga_scu: float | None = None
    minerio_scu: float | None = None
    casco_hp: float | None = None
    armadura_hp: float | None = None
    escudo_hp: float | None = None
    escudo_regen: float | None = None  # HP/s
    escudo_tipo: str = ""
    velocidade_scm: float | None = None   # m/s
    velocidade_max: float | None = None   # m/s
    boost: float | None = None            # m/s
    pitch: float | None = None            # °/s
    yaw: float | None = None
    roll: float | None = None
    quantum_velocidade: float | None = None  # m/s
    quantum_alcance: float | None = None     # m
    quantum_spool: float | None = None       # s
    dps_piloto: float | None = None
    dps_piloto_sustentado: float | None = None
    alpha_piloto: float | None = None
    dps_torretas: float | None = None
    misseis: int | None = None
    dano_misseis: float | None = None
    armas: list[Arma] = field(default_factory=list)
    seguro_min: float | None = None         # tempo de resgate
    seguro_expresso_min: float | None = None
    seguro_expresso_custo: float | None = None
    preco_jogo: float | None = None          # menor preço de compra (aUEC)
    preco_jogo_local: str = ""
    aluguel: float | None = None             # menor aluguel (aUEC/dia)
    aluguel_local: str = ""
    preco_dolar: float | None = None         # pledge (USD)
    versao: str = ""

    @property
    def dps_total(self) -> float | None:
        partes = [v for v in (self.dps_piloto, self.dps_torretas) if v is not None]
        return sum(partes) if partes else None

    @property
    def hp_total(self) -> float | None:
        """Casco + escudo: quanto dano a nave aguenta antes de cair (aproximado)."""
        partes = [v for v in (self.casco_hp, self.escudo_hp) if v is not None]
        return sum(partes) if partes else None

    @property
    def carreira_pt(self) -> str:
        return tr(CARREIRAS[self.carreira.lower()]) if self.carreira.lower() in CARREIRAS else self.carreira

    @property
    def tamanho_pt(self) -> str:
        return tr(TAMANHOS[self.tamanho.lower()]) if self.tamanho.lower() in TAMANHOS else self.tamanho

    @property
    def chaves(self) -> list[str]:
        """Nomes normalizados pelos quais outros módulos reconhecem esta nave.

        Inclui o nome com e sem o fabricante ("MISC Prospector" e "Prospector").
        """
        nomes = {self.nome, self.nome_jogo}
        for n in list(nomes):
            for prefixo in (self.codigo_fabricante, self.fabricante):
                if prefixo and n.lower().startswith(prefixo.lower() + " "):
                    nomes.add(n[len(prefixo) + 1:])
            partes = (self.fabricante or "").split()
            if partes and n.lower().startswith(partes[0].lower() + " "):  # "Aegis Dynamics" -> "Aegis"
                nomes.add(n[len(partes[0]) + 1:])
        return sorted({chave_nome(n) for n in nomes if chave_nome(n)})

    @classmethod
    def de_wiki(cls, d: dict[str, Any]) -> "FichaNave":
        fab = d.get("manufacturer") or {}
        crew = d.get("crew") or {}
        escudo = d.get("shield") or {}
        vel = d.get("speed") or {}
        agil = d.get("agility") or {}
        qt = d.get("quantum") or {}
        arm = d.get("weaponry") or {}
        seg = d.get("insurance") or {}

        # Armas fixas do piloto, agrupadas por nome
        contagem: dict[str, list[float]] = {}
        for w in ((arm.get("fixed_weapons") or {}).get("weapons") or []):
            contagem.setdefault(str(w.get("name") or "?"), []).append(_num(w.get("dps")) or 0.0)
        armas = [Arma(n, sum(v) / len(v), len(v)) for n, v in contagem.items()]
        armas.sort(key=lambda a: -a.dps * a.quantidade)

        compra = _mais_barato((d.get("uex_prices") or {}).get("purchase"), "price_buy")
        aluguel = _mais_barato((d.get("uex_prices") or {}).get("rental"), "price_rent")
        misseis = (arm.get("missiles") or {}).get("count")
        tmin, tmax = _num(crew.get("min")), _num(crew.get("max"))

        # A Wiki às vezes inclui a sigla do fabricante no nome ("MISC Prospector", mas "Gladius")
        nome = str(d.get("name") or d.get("game_name") or "?").strip()
        sigla = str(fab.get("code") or "")
        if sigla and nome.lower().startswith(sigla.lower() + " ") and len(nome) > len(sigla) + 1:
            nome = nome[len(sigla) + 1:]

        return cls(
            uuid=str(d.get("uuid") or ""),
            nome=nome,
            nome_jogo=str(d.get("game_name") or "").strip(),
            fabricante=str(fab.get("name") or ""),
            codigo_fabricante=str(fab.get("code") or ""),
            classe=str(d.get("class_name") or ""),
            terrestre=bool(d.get("is_vehicle")) and not bool(d.get("is_spaceship")),
            tamanho=_en(d.get("size")),
            carreira=str(d.get("career") or _en(d.get("type")) or ""),
            funcao=str(d.get("role") or ""),
            status=_en(d.get("production_status")),
            tripulacao_min=int(tmin) if tmin else None,
            tripulacao_max=int(tmax) if tmax else None,
            carga_scu=_num(d.get("cargo_capacity")),
            minerio_scu=_num(d.get("ore_capacity")),
            casco_hp=_num(d.get("health")),
            armadura_hp=_num((d.get("armor") or {}).get("health")),
            escudo_hp=_num(escudo.get("hp")),
            escudo_regen=_num(escudo.get("regeneration")),
            escudo_tipo=str(escudo.get("face_type") or ""),
            velocidade_scm=_num(vel.get("scm")),
            velocidade_max=_num(vel.get("max")),
            boost=_num(vel.get("boost_forward")),
            pitch=_num(agil.get("pitch")),
            yaw=_num(agil.get("yaw")),
            roll=_num(agil.get("roll")),
            quantum_velocidade=_num(qt.get("quantum_speed")),
            quantum_alcance=_num(qt.get("quantum_range")),
            quantum_spool=_num(qt.get("quantum_spool_time")),
            dps_piloto=_num(arm.get("pilot_dps")),
            dps_piloto_sustentado=_num(arm.get("pilot_sustained_dps")),
            alpha_piloto=_num(arm.get("pilot_alpha")),
            dps_torretas=_num(arm.get("turret_dps")),
            misseis=int(misseis) if misseis else None,
            dano_misseis=_num(arm.get("total_missile_damage")),
            armas=armas,
            seguro_min=_num(seg.get("claim_time")),
            seguro_expresso_min=_num(seg.get("expedite_time")),
            seguro_expresso_custo=_num(seg.get("expedite_cost")),
            preco_jogo=compra[0] if compra else None,
            preco_jogo_local=compra[1] if compra else "",
            aluguel=aluguel[0] if aluguel else None,
            aluguel_local=aluguel[1] if aluguel else "",
            preco_dolar=_num(d.get("msrp")) or None,
            versao=str(d.get("version") or "").split("-")[0],
        )


def _mais_barato(precos: Any, campo: str) -> tuple[float, str] | None:
    melhor: tuple[float, str] | None = None
    for p in precos or []:
        valor = _num(p.get(campo)) if isinstance(p, dict) else None
        if not valor or valor <= 0:
            continue
        local = str(p.get("terminal_name") or "")
        if p.get("star_system_name"):
            local = f"{local} ({p['star_system_name']})"
        if melhor is None or valor < melhor[0]:
            melhor = (valor, local)
    return melhor


def _sufixo(classe: str) -> str:
    """Última parte do class_name para diferenciar variantes: "DRAK_Corsair_Exec_Military" -> "Military"."""
    partes = [p for p in classe.split("_") if p]
    return partes[-1] if partes else ""


def fichas_de_wiki(linhas: Iterable[dict[str, Any]]) -> list[FichaNave]:
    """Fichas ordenadas por nome, sem maquetes e com nomes únicos.

    Nomes repetidos com as mesmas estatísticas (ex.: pintura Best in Show) ficam só
    uma vez; variantes diferentes com o mesmo nome ganham um sufixo: "Corsair PYAM Exec (Military)".
    """
    por_nome: dict[str, list[FichaNave]] = {}
    for d in linhas or []:
        if not isinstance(d, dict) or _CLASSES_IGNORADAS.search(str(d.get("class_name") or "")):
            continue
        f = FichaNave.de_wiki(d)
        if f.uuid:
            por_nome.setdefault(f.nome, []).append(f)

    saida: list[FichaNave] = []
    for nome, grupo in por_nome.items():
        # Mesmas estatísticas = mesma nave: fica a de class_name mais curto (a "original")
        unicas: dict[tuple, FichaNave] = {}
        for f in sorted(grupo, key=lambda f: (len(f.classe), f.classe)):
            assinatura = (f.casco_hp, f.escudo_hp, f.dps_total, f.carga_scu, f.velocidade_scm)
            unicas.setdefault(assinatura, f)
        variantes = list(unicas.values())
        if len(variantes) > 1:
            for f in variantes:
                f.nome = f"{nome} ({_sufixo(f.classe)})"
        saida.extend(variantes)

    vistos: dict[str, int] = {}  # garantia final: nenhum nome repetido
    for f in saida:
        n = vistos.get(f.nome, 0) + 1
        vistos[f.nome] = n
        if n > 1:
            f.nome = f"{f.nome} #{n}"
    return sorted(saida, key=lambda f: f.nome.lower())


def encontrar(fichas: Iterable[FichaNave], uuid: str = "", nome: str = "") -> FichaNave | None:
    """Procura pelo uuid; se não achar (a Wiki mudou), pelo nome."""
    lista = list(fichas)
    if uuid:
        achada = next((f for f in lista if f.uuid == uuid), None)
        if achada:
            return achada
    chave = chave_nome(nome)
    return next((f for f in lista if chave and chave in (chave_nome(f.nome), *f.chaves)), None) if chave else None
