"""Identificação da assinatura do scan (portado do Beto Scanner sem mudar a regra).

O número do ping é sempre: assinatura base × quantidade de rochas.
Ex.: 17.080 = 4 × 4.270 -> 4 rochas de Iron.

Os candidatos mantêm o formato do scanner antigo (chaves "sig", "count",
"diff", "exact", "likely") para o histórico importado continuar válido.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

Candidato = dict[str, Any]


def carregar_assinaturas(arquivo: Path) -> list[dict[str, Any]]:
    with open(arquivo, "r", encoding="utf-8") as f:
        return json.load(f)["signatures"]


def identificar(valor: int, assinaturas: list[dict[str, Any]], max_quantidade: int = 12,
                tolerancia: float = 0.004) -> list[Candidato]:
    """Candidatos para um valor de scan: exatos primeiro, depois prováveis, depois menor quantidade.

    Sem match exato, tenta aproximado (o OCR pode ter errado um dígito), marcado com exact=False.
    """
    def buscar(tol_abs: float) -> list[Candidato]:
        saida = []
        for s in assinaturas:
            base = s["base"]
            n = int(round(valor / base))
            if n < 1 or n > max_quantidade:
                continue
            dif = abs(valor - n * base)
            if dif <= tol_abs:
                saida.append({
                    "sig": s, "count": n, "diff": dif, "exact": dif == 0,
                    "likely": n <= s.get("cluster_max", max_quantidade),
                })
        saida.sort(key=lambda c: (c["diff"], not c["likely"], c["count"]))
        return saida

    exatos = buscar(0)
    if exatos:
        return exatos
    aprox = buscar(max(10, valor * tolerancia))
    if aprox:
        aprox = [c for c in aprox if c["diff"] <= aprox[0]["diff"] + 10]
    return aprox[:3]


# ---------------------------------------------------------------- leitura de números do OCR
_CORRIGE = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "a": "0", "U": "0",
                          "I": "1", "l": "1", "|": "1", "i": "1", "!": "1", "J": "1", "]": "1",
                          "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "g": "9", "G": "6",
                          "e": "6", "E": "6", "b": "6", "T": "7"})
_PARECE_NUMERO = re.compile(
    r"^[\dOoDQaUIl|i!J\]SsBZzgGeEbT]{1,3}([.,][\dOoDQaUIl|i!J\]SsBZzgGeEbT]{3})+$|^\d{4,6}$"
)


def extrair_numeros(texto: str, minimo: int, maximo: int) -> list[tuple[int, bool]]:
    """Números do texto do OCR e se vieram limpos (True) ou corrigidos (False).

    Aceita "16,000", "16.000", "16000" e corrige letras confundidas com dígitos
    ("IS,ooo" -> 15000), mas só em trechos com formato de número.
    """
    numeros: list[tuple[int, bool]] = []
    vistos: set[int] = set()
    for tok in re.split(r"\s+", texto.strip()):
        tok = tok.strip("()[]{}<>'\"`*~:;")
        if not tok or not _PARECE_NUMERO.match(tok):
            continue
        limpo = bool(re.fullmatch(r"[\d.,]+", tok))
        v = int(re.sub(r"[^\d]", "", tok.translate(_CORRIGE)) or 0)
        if minimo <= v <= maximo and v not in vistos:
            vistos.add(v)
            numeros.append((v, limpo))
    return numeros
