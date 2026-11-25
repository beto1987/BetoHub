"""Cálculo de quebra (fratura) da rocha e leitura do painel SCAN RESULTS.

Portado do mining.py do Beto Scanner. Fórmula das calculadoras da comunidade:
    potência necessária  = (massa / (1 - resistência_ajustada/100)) / 5
    resistência_ajustada = resistência da rocha × produto dos modificadores
Potência disponível = soma da potência máxima de cada laser × modificadores dos módulos.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

Loadout = dict[str, Any]  # {"ship": "Prospector", "lasers": [{"head": ..., "modules": [...]}]}


class DadosMineracao:
    """Naves, cabeças de laser, módulos e gadgets (mining_data.json)."""

    def __init__(self, arquivo: Path):
        with open(arquivo, "r", encoding="utf-8") as f:
            d = json.load(f)
        self.naves: dict[str, Any] = d["ships"]
        self.cabecas: dict[str, Any] = d["heads"]
        self.modulos: dict[str, Any] = d["modules"]
        self.gadgets: dict[str, Any] = d["gadgets"]

    def loadout_padrao(self, nave: str) -> Loadout:
        s = self.naves[nave]
        return {"ship": nave, "lasers": [{"head": s["default_head"], "modules": []} for _ in range(s["lasers"])]}

    def cabecas_da_nave(self, nave: str) -> list[str]:
        s = self.naves[nave]
        if s.get("only"):
            return list(s["only"])
        return [n for n, h in self.cabecas.items() if h["size"] == s["size"]]

    def normalizar(self, lo: Loadout | None) -> Loadout:
        """Garante um loadout válido (nave conhecida, nº de lasers certo, cabeças compatíveis)."""
        if not lo or lo.get("ship") not in self.naves:
            return self.loadout_padrao("Prospector" if "Prospector" in self.naves else next(iter(self.naves)))
        nave = lo["ship"]
        s = self.naves[nave]
        cabecas = self.cabecas_da_nave(nave)
        lasers = [dict(l) for l in lo.get("lasers", [])][: s["lasers"]]
        while len(lasers) < s["lasers"]:
            lasers.append({"head": s["default_head"], "modules": []})
        for l in lasers:
            if l.get("head") not in cabecas:
                l["head"], l["modules"] = s["default_head"], []
            slots = self.cabecas[l["head"]]["slots"]
            l["modules"] = [m for m in l.get("modules", []) if m in self.modulos][:slots]
        return {"ship": nave, "lasers": lasers}

    # ------------------------------------------------------------ cálculo
    def _somar(self, lo: Loadout, usar_ativos: bool) -> tuple[float, float, float]:
        """(potência total, mult. de resistência, mult. de instabilidade).

        Vários lasers (MOLE): potências somam; modificadores de resistência de
        lasers diferentes não se acumulam (média, como nas calculadoras).
        """
        potencia, res, inst = 0.0, [], []
        for laser in lo.get("lasers", []):
            cab = self.cabecas.get(laser.get("head"))
            if not cab:
                continue
            p, r, i = cab["max"], cab["resistance"], cab["instability"]
            for m in laser.get("modules", [])[: cab["slots"]]:
                mod = self.modulos.get(m)
                if not mod or (mod["type"] == "ativo" and not usar_ativos):
                    continue
                p *= mod["power"]
                r *= mod["resistance"]
                i *= mod["instability"]
            potencia += p
            res.append(r)
            inst.append(i)
        if not res:
            return 0.0, 1.0, 1.0
        return potencia, sum(res) / len(res), sum(inst) / len(inst)

    def tem_ativos(self, lo: Loadout) -> bool:
        return any(self.modulos.get(m, {}).get("type") == "ativo"
                   for l in lo.get("lasers", []) for m in l.get("modules", []))

    def avaliar(self, lo: Loadout, massa: float, resistencia: float, instabilidade: float | None = None,
                gadget: str | None = None, usar_ativos: bool = False) -> dict[str, Any]:
        potencia, mult_res, mult_inst = self._somar(lo, usar_ativos)
        if gadget:
            g = self.gadgets[gadget]
            mult_res *= g["resistance"]
            mult_inst *= g["instability"]
        res_aj = resistencia * mult_res
        necessaria = potencia_necessaria(massa, res_aj)
        return {
            "power": potencia, "required": necessaria, "adj_resistance": res_aj,
            "adj_instability": instabilidade * mult_inst if instabilidade is not None else None,
            "breaks": potencia >= necessaria,
            "throttle": necessaria / potencia * 100.0 if potencia else float("inf"),
            "gadget": gadget, "use_active": usar_ativos,
        }

    def analisar(self, lo: Loadout, massa: float, resistencia: float,
                 instabilidade: float | None = None) -> dict[str, Any]:
        """Sem ativos, com ativos e gadgets que resolvem (quando não quebra)."""
        saida = {"base": self.avaliar(lo, massa, resistencia, instabilidade),
                 "active": None, "gadgets": []}
        ativos = self.tem_ativos(lo)
        if ativos:
            saida["active"] = self.avaliar(lo, massa, resistencia, instabilidade, None, True)
        if not (saida["base"]["breaks"] or (saida["active"] and saida["active"]["breaks"])):
            for g in self.gadgets:
                for usar in ([False, True] if ativos else [False]):
                    r = self.avaliar(lo, massa, resistencia, instabilidade, g, usar)
                    if r["breaks"]:
                        saida["gadgets"].append(r)
                        break
            saida["gadgets"].sort(key=lambda r: (r["use_active"], r["throttle"]))
        return saida


def potencia_necessaria(massa: float, resistencia_pct: float) -> float:
    if resistencia_pct >= 100:
        return float("inf")
    return (massa / (1 - resistencia_pct / 100.0)) / 5.0


# ---------------------------------------------------------------- leitura do painel de scan
_CORRIGE = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "|": "1",
                          "i": "1", "S": "5", "s": "5", "B": "8", "Z": "2", "g": "9"})
DIFICULDADES = ("EASY", "MEDIUM", "HARD", "EXTREME", "IMPOSSIBLE", "CHALLENGING", "TRIVIAL")


def rotulo(tok: str) -> str | None:
    t = re.sub(r"[^A-Za-z0-9]", "", tok).upper()
    if not t:
        return None
    if t in ("MASS", "MASSA", "NASS", "HASS", "MA55", "MAS5", "MASS1") or (
            re.fullmatch(r"[MNH]?A?[S5]{2}A?", t) and len(t) >= 3):
        return "mass"
    if t.startswith(("RES", "RE5", "R3S")):
        return "resistance"
    if t.startswith(("INST", "1NST", "LNST", "INS7")) or t == "INS":
        return "instability"
    return None


def para_numero(s: str, tipo: str) -> float | None:
    s = re.sub(r"[^\d.,]", "", s.translate(_CORRIGE))
    if not s or not re.search(r"\d", s):
        return None
    if tipo == "mass":
        if re.fullmatch(r"\d+[.,]\d{1,2}", s):
            return None                    # "14.78": número cortado, não confiar
        v = float(re.sub(r"[.,]", "", s))  # separador de milhar some
        return v if v >= 100 else None     # pedaço cortado não é massa
    s = s.replace(",", ".")
    if s.count(".") > 1:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def ler_painel_por_posicao(palavras: list[tuple[str, float, float, float, float]]) -> dict[str, Any]:
    """Massa/resistência/instabilidade usando a POSIÇÃO das palavras (valor à direita do rótulo)."""
    rotulos = [(k, p) for p in palavras for k in [rotulo(p[0])] if k]
    saida: dict[str, Any] = {}
    for tipo, (_txt, x, y, w, h) in rotulos:
        if tipo in saida:
            continue
        cy = y + h / 2
        linha = sorted((v for v in palavras
                        if v[1] > x + w * 0.6 and abs((v[2] + v[4] / 2) - cy) < max(h, v[4]) * 0.6
                        and not rotulo(v[0])), key=lambda v: v[1])
        if not linha:
            continue
        valor, fim = linha[0][0], linha[0][1] + linha[0][3]
        for v in linha[1:]:  # junta pedaços colados ("15" "824")
            if v[1] - fim < h * 0.8 and re.fullmatch(r"[\dOoIlSsB.,%]+", v[0]):
                valor += v[0]
                fim = v[1] + v[3]
            else:
                break
        num = para_numero(valor, tipo)
        if num is None or (tipo == "resistance" and not 0 <= num <= 100):
            continue
        saida[tipo] = num
    for v in palavras:
        t = re.sub(r"[^A-Z]", "", v[0].upper())
        if t in DIFICULDADES:
            saida["difficulty"] = t
    return saida


def ler_painel_por_texto(texto: str) -> dict[str, Any]:
    """Plano B só com texto: exige o rótulo colado no valor."""
    t = texto.replace("\n", " ")
    saida: dict[str, Any] = {}
    for tipo, padrao in (("mass", r"\b[MNH]?A?SSA?\s*[:;]?\s*([\dOoIlSB][\dOoIlSB.,]{2,})"),
                         ("resistance", r"\bRES\w*\s*[:;]?\s*([\dOoIlSB][\dOoIlSB.,]*)\s*%"),
                         ("instability", r"\bINST\w*\s*[:;]?\s*([\dOoIlSB][\dOoIlSB.,]*)")):
        m = re.search(padrao, t, re.I)
        if m:
            n = para_numero(m.group(1), tipo)
            if n is not None:
                saida[tipo] = n
    if saida.get("resistance") is not None and not 0 <= saida["resistance"] <= 100:
        saida.pop("resistance")
    for d in DIFICULDADES:
        if d in t.upper():
            saida["difficulty"] = d
    return saida
