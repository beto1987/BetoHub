"""Importa a configuração e o histórico do Beto Scanner antigo (uma vez só).

Procura nas pastas conhecidas e usa o config.json mais recente:
  - D:\\Claudinho\\SCScanner (versão em script)
  - %LOCALAPPDATA%\\Programs\\StarCitizenBetoScanner (versão instalada)
Nada é alterado nas pastas antigas.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PASTAS_CONHECIDAS = [
    Path(r"D:\Claudinho\SCScanner"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "StarCitizenBetoScanner",
]

# chave antiga (config.json) -> chave nova ([modulos.mineracao])
MAPA = {
    "region": "regiao_numero",
    "rock_region": "regiao_rocha",
    "interval_ms": "intervalo_ms",
    "scale": "escala",
    "threshold": "limiar",
    "dark_text": "texto_escuro",
    "min_value": "valor_minimo",
    "max_value": "valor_maximo",
    "max_count": "max_quantidade",
    "fuzzy_tolerance": "tolerancia",
    "ocr_engine": "motor_ocr",
    "ocr_lang": "idioma_ocr",
    "tesseract_cmd": "tesseract_cmd",
    "refinery_top": "refinarias_mostradas",
    "mining": "loadout",
}


def encontrar_config(pastas: list[Path] | None = None) -> Path | None:
    candidatos = [p / "config.json" for p in (pastas or PASTAS_CONHECIDAS) if str(p) and (p / "config.json").is_file()]
    return max(candidatos, key=lambda c: c.stat().st_mtime) if candidatos else None


def converter_config(antiga: dict[str, Any]) -> dict[str, Any]:
    """Só leva chaves conhecidas e com valor (None é ignorado)."""
    return {nova: antiga[velha] for velha, nova in MAPA.items() if antiga.get(velha) is not None}


def importar(pastas: list[Path] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Devolve (opções novas, histórico antigo, pasta de origem). Vazio se nada encontrado."""
    arquivo = encontrar_config(pastas)
    if arquivo is None:
        return {}, [], ""
    with open(arquivo, "r", encoding="utf-8") as f:
        opcoes = converter_config(json.load(f))

    historico: list[dict[str, Any]] = []
    arq_hist = arquivo.with_name("history.json")
    if arq_hist.is_file():
        try:
            with open(arq_hist, "r", encoding="utf-8") as f:
                dados = json.load(f)
            historico = [h for h in dados if isinstance(h, dict) and h.get("results")]
        except (OSError, ValueError):
            historico = []
    return opcoes, historico, str(arquivo.parent)
