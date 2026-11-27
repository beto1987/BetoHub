"""Planejador de rota das entregas dos contratos de transporte. Sem Qt, testável.

1. `paradas_dos_contratos`: lê os objetivos "Deliver 0/8 SCU of Iron to HUR-L1 Green Glade Station"
   dos contratos ativos e a coleta do título ("... | from ArcCorp Mining Area 056").
2. `IndiceLocais`: casa o nome do local com os terminais da UEX (estação, cidade, posto).
   Destinos genéricos ("Pyro System") ficam sem local: o jogador escolhe.
3. `melhor_rota`: ordem das paradas com a menor distância total (distâncias da UEX),
   sempre coletando antes de entregar a carga do mesmo contrato.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from beto_hub.core.i18n import N_, tr
from beto_hub.core.texto import chave_nome

from .eventos import local_do_titulo
from .repositorio import OBJ_ATIVO, Contrato

COLETA, ENTREGA = "coleta", "entrega"
PENALIDADE_GM = 1000.0     # distância desconhecida na UEX: conta como "muito longe"
LIMITE_EXATO = 10          # até 10 locais: busca exata; acima, aproximação

_RE_ENTREGA = re.compile(r"^Deliver\s+(?:(?P<feito>\d+)/(?P<total>\d+)\s+)?(?:(?P<unidade>SCU of|Cargo Boxes?)\s+)?"
                         r"(?P<carga>.*?)\s+[Tt]o\s+(?P<destino>.+?)\s*$")
_RE_COLETA = re.compile(r"^(?:Collect|Pick up|Pickup)\s+(?P<carga>.*?)\s+[Ff]rom\s+(?P<origem>.+?)\s*$")
_RE_SISTEMA = re.compile(r"^(?P<sistema>[\w\- ]+?)\s+System$", re.I)


# ---------------------------------------------------------------- locais (terminais da UEX)
@dataclass(frozen=True)
class Local:
    nome: str
    id_terminal: int     # terminal representativo (para as distâncias da UEX)
    sistema: str = ""

    @property
    def rotulo(self) -> str:
        return f"{self.nome} ({self.sistema})" if self.sistema else self.nome


class IndiceLocais:
    """Locais (estações, cidades, postos) a partir dos terminais da UEX."""

    # Do nome de lugar ao nome de terminal (a lista prefere "Area18" a "TDD Area 18")
    _CAMPOS = ("space_station_name", "city_name", "outpost_name", "displayname", "nickname")

    def __init__(self, terminais: Iterable[dict[str, Any]]):
        candidatos: dict[str, list[dict[str, Any]]] = {}
        nomes: dict[str, str] = {}
        self._prioridade: dict[str, int] = {}
        for t in terminais or []:
            if not isinstance(t, dict) or not t.get("id") or t.get("is_available_live") == 0:
                continue
            for prioridade, campo in enumerate(self._CAMPOS):
                nome = str(t.get(campo) or "").strip()
                if nome:
                    chave = chave_nome(nome)
                    candidatos.setdefault(chave, []).append(t)
                    nomes.setdefault(chave, nome)
                    self._prioridade[chave] = min(prioridade, self._prioridade.get(chave, prioridade))
        self._por_chave: dict[str, Local] = {}
        for chave, lista in candidatos.items():
            # Representante: terminal de commodities (é o que a UEX mais usa nas distâncias), menor id
            t = min(lista, key=lambda x: (x.get("type") != "commodity", int(x.get("id") or 0)))
            self._por_chave[chave] = Local(nomes[chave], int(t["id"]), str(t.get("star_system_name") or ""))

    def __len__(self) -> int:
        return len(self._por_chave)

    def casar(self, nome: str) -> Local | None:
        return self._por_chave.get(chave_nome(nome)) if nome else None

    def todos(self) -> list[Local]:
        """Locais únicos (um por terminal representativo, com o nome do lugar), em ordem alfabética."""
        unicos: dict[int, tuple[tuple[int, int], Local]] = {}
        for chave, l in self._por_chave.items():
            ordem = (self._prioridade[chave], len(l.nome))
            if l.id_terminal not in unicos or ordem < unicos[l.id_terminal][0]:
                unicos[l.id_terminal] = (ordem, l)
        return sorted((l for _, l in unicos.values()), key=lambda l: l.rotulo.lower())


# ---------------------------------------------------------------- paradas
@dataclass
class Parada:
    tipo: str                # COLETA | ENTREGA
    missao: str
    contrato: str            # rótulo do contrato
    texto_local: str         # como veio do log ("HUR-L1 Green Glade Station", "Pyro System")
    carga: str = ""
    scu: float | None = None  # quanto falta entregar
    local: Local | None = None
    incluir: bool = True
    objetivo: str = ""

    @property
    def sistema_sugerido(self) -> str:
        m = _RE_SISTEMA.match(self.texto_local or "")
        return m.group("sistema") if m else ""

    @property
    def descricao(self) -> str:
        if not self.carga:
            return tr("Coletar") if self.tipo == COLETA else tr("Entregar")
        if self.scu:
            modelo = N_("Coletar {scu} SCU de {carga}") if self.tipo == COLETA else N_("Entregar {scu} SCU de {carga}")
            return tr(modelo, scu=f"{self.scu:g}", carga=tr(self.carga))
        modelo = N_("Coletar {carga}") if self.tipo == COLETA else N_("Entregar {carga}")
        return tr(modelo, carga=tr(self.carga))


def ler_entrega(texto: str) -> dict[str, Any] | None:
    """"Deliver 2/8 SCU of Iron to HUR-L1 Green Glade Station" -> carga, falta (6), destino."""
    m = _RE_ENTREGA.match((texto or "").strip())
    if not m:
        return None
    feito, total = m.group("feito"), m.group("total")
    falta = (int(total) - int(feito)) if feito and total else None
    unidade = (m.group("unidade") or "").lower()
    return {"carga": m.group("carga").strip(), "falta": falta if "scu" in unidade or not unidade else None,
            "destino": m.group("destino").strip()}


def paradas_dos_contratos(contratos: Iterable[Contrato], indice: IndiceLocais | None = None) -> list[Parada]:
    """Paradas das entregas pendentes dos contratos ativos (só objetivos de entrega/coleta)."""
    paradas: list[Parada] = []
    for c in contratos:
        if not c.ativo:
            continue
        entregas: list[Parada] = []
        coletas: list[Parada] = []
        for o in c.objetivos:
            if o.status != OBJ_ATIVO:
                continue
            e = ler_entrega(o.texto)
            if e:
                if e["falta"] == 0:
                    continue
                entregas.append(Parada(ENTREGA, c.missao, c.rotulo, e["destino"], e["carga"], e["falta"],
                                       objetivo=o.id))
                continue
            m = _RE_COLETA.match(o.texto or "")
            if m:
                coletas.append(Parada(COLETA, c.missao, c.rotulo, m.group("origem").strip(), m.group("carga").strip(),
                                      objetivo=o.id))
        if not entregas:
            continue
        # Coleta pelo título ("... | from X"): só se nada foi entregue ainda (senão a carga já está a bordo)
        origem = local_do_titulo(c.titulo) if " from " in f" {c.titulo.lower()} " else ""
        algo_entregue = any(o.status != OBJ_ATIVO for o in c.objetivos)
        if origem and not coletas and not algo_entregue:
            coletas.append(Parada(COLETA, c.missao, c.rotulo, origem, N_("carga do contrato")))
        paradas.extend(coletas + entregas)
    if indice is not None:
        for p in paradas:
            p.local = indice.casar(p.texto_local)
    return paradas


# ---------------------------------------------------------------- rota
@dataclass
class Trecho:
    local: Local
    paradas: list[Parada]
    distancia: float | None   # Gm desde o ponto anterior (None = desconhecida ou início)


@dataclass
class Rota:
    trechos: list[Trecho] = field(default_factory=list)
    total_gm: float = 0.0
    desconhecidas: int = 0          # trechos sem distância na UEX
    exata: bool = True              # False = aproximação (muitos locais)
    avisos: list[str] = field(default_factory=list)
    total_valido: bool = True       # False = paradas removidas depois do cálculo (precisa recalcular)


Distancia = Callable[[int, int], "float | None"]


def melhor_rota(paradas: list[Parada], distancia: Distancia, inicio: Local | None = None) -> Rota:
    """Menor distância total visitando cada local uma vez, com coleta antes da entrega."""
    validas = [p for p in paradas if p.incluir and p.local is not None]
    rota = Rota()
    sem_local = [p for p in paradas if p.incluir and p.local is None]
    if sem_local:
        rota.avisos.append(tr("{n} parada(s) sem local definido ficaram de fora.", n=len(sem_local)))
    if not validas:
        return rota

    # Agrupa por local (várias entregas no mesmo lugar = uma parada)
    locais: list[Local] = []
    grupos: dict[int, list[Parada]] = {}
    for p in validas:
        if p.local.id_terminal not in grupos:
            locais.append(p.local)
            grupos[p.local.id_terminal] = []
        grupos[p.local.id_terminal].append(p)
    n = len(locais)
    pos = {l.id_terminal: i for i, l in enumerate(locais)}

    # Precedência: local da coleta de um contrato vem antes dos locais das entregas dele
    antes: list[set[int]] = [set() for _ in range(n)]
    for p in validas:
        if p.tipo == ENTREGA:
            for q in validas:
                if q.tipo == COLETA and q.missao == p.missao and q.local.id_terminal != p.local.id_terminal:
                    antes[pos[p.local.id_terminal]].add(pos[q.local.id_terminal])
    if _tem_ciclo(antes):
        rota.avisos.append(tr("Coletas e entregas em conflito: a ordem coleta→entrega foi ignorada."))
        antes = [set() for _ in range(n)]

    cache: dict[tuple[int, int], float | None] = {}

    def d(a: Local | None, b: Local) -> float:
        if a is None or a.id_terminal == b.id_terminal:
            return 0.0
        chave = (a.id_terminal, b.id_terminal)
        if chave not in cache:
            cache[chave] = distancia(a.id_terminal, b.id_terminal)
        v = cache[chave]
        return PENALIDADE_GM if v is None else float(v)

    def custo(i: int, j: int) -> float:
        """i = -1 é o ponto de partida (sem partida: o primeiro trecho não conta)."""
        return d(inicio if i < 0 else locais[i], locais[j])

    if n <= LIMITE_EXATO:
        ordem = _busca_exata(n, antes, custo)
    else:
        rota.exata = False
        ordem = _vizinho_mais_proximo(n, antes, custo)
        rota.avisos.append(tr("{n} locais: rota aproximada (vizinho mais próximo).", n=n))

    anterior = inicio
    for i in ordem:
        local = locais[i]
        if anterior is None:
            dist = None
        elif anterior.id_terminal == local.id_terminal:
            dist = 0.0
        else:
            dist = cache.get((anterior.id_terminal, local.id_terminal), distancia(anterior.id_terminal, local.id_terminal))
            if dist is None:
                rota.desconhecidas += 1
            else:
                rota.total_gm += float(dist)
        # coletas primeiro dentro do mesmo local
        rota.trechos.append(Trecho(local, sorted(grupos[local.id_terminal], key=lambda p: p.tipo != COLETA), dist))
        anterior = local
    if rota.desconhecidas:
        rota.avisos.append(tr("{n} trecho(s) sem distância na UEX (não somados ao total).", n=rota.desconhecidas))
    return rota


def _tem_ciclo(antes: list[set[int]]) -> bool:
    estado = [0] * len(antes)  # 0 novo, 1 visitando, 2 feito

    def visita(i: int) -> bool:
        estado[i] = 1
        for j in antes[i]:
            if estado[j] == 1 or (estado[j] == 0 and visita(j)):
                return True
        estado[i] = 2
        return False

    return any(estado[i] == 0 and visita(i) for i in range(len(antes)))


def _busca_exata(n: int, antes: list[set[int]], custo: Callable[[int, int], float]) -> list[int]:
    """Branch and bound: todas as ordens válidas, cortando as que já passam da melhor."""
    melhor: list[float | list[int]] = [float("inf"), list(range(n))]
    visitados = [False] * n
    caminho: list[int] = []

    def buscar(atual: int, acumulado: float) -> None:
        if acumulado >= melhor[0]:
            return
        if len(caminho) == n:
            melhor[0], melhor[1] = acumulado, list(caminho)
            return
        opcoes = [j for j in range(n) if not visitados[j] and all(visitados[k] for k in antes[j])]
        opcoes.sort(key=lambda j: custo(atual, j))  # mais perto primeiro: acha boas rotas cedo
        for j in opcoes:
            visitados[j] = True
            caminho.append(j)
            buscar(j, acumulado + custo(atual, j))
            caminho.pop()
            visitados[j] = False

    buscar(-1, 0.0)
    return melhor[1]  # type: ignore[return-value]


def _vizinho_mais_proximo(n: int, antes: list[set[int]], custo: Callable[[int, int], float]) -> list[int]:
    visitados = [False] * n
    ordem: list[int] = []
    atual = -1
    while len(ordem) < n:
        opcoes = [j for j in range(n) if not visitados[j] and all(visitados[k] for k in antes[j])]
        j = min(opcoes, key=lambda j: custo(atual, j))
        visitados[j] = True
        ordem.append(j)
        atual = j
    return ordem
