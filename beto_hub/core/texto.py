"""Utilidades de texto compartilhadas pelos módulos (sem Qt)."""

from __future__ import annotations

import re
import unicodedata


def chave_nome(nome: str) -> str:
    """Nome normalizado para comparar entre fontes de dados (UEX, Wiki, arquivos locais).

    Sem acentos, minúsculo e só letras e números: "Gatac Hyūn" -> "gatachyun".
    """
    sem_acento = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())
