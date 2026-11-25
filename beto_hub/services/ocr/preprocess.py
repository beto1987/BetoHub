"""Preparo da imagem para o OCR (igual ao Beto Scanner).

O texto do HUD é pequeno e colorido: ampliamos, aumentamos o contraste e
deixamos preto no branco. Como cada cena tem luz diferente, várias
variações (modo + limiar) são tentadas e o resultado mais lido vence.
"""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageChops, ImageOps


def preprocessar(img: Image.Image, opcoes: dict[str, Any], limiar: int | None = None,
                 modo: str = "lum") -> Image.Image:
    """modo: "lum" (luminância), "max" (canal mais forte, bom para HUD colorido),
    "gray" (sem binarizar, só amplia e realça)."""
    escala = max(1, int(opcoes.get("escala", 3)))
    if modo == "max":
        r, g_, b = img.convert("RGB").split()
        g = ImageChops.lighter(ImageChops.lighter(r, g_), b)
    else:
        g = img.convert("L")
    g = g.resize((g.width * escala, g.height * escala), Image.LANCZOS)
    g = ImageOps.autocontrast(g, cutoff=1)
    texto_escuro = bool(opcoes.get("texto_escuro", False))

    if modo == "gray":
        pb = g if texto_escuro else ImageOps.invert(g)
    else:
        lim = int(opcoes.get("limiar", 140) if limiar is None else limiar)
        if texto_escuro:
            pb = g.point(lambda p: 0 if p < lim else 255)
        else:
            pb = g.point(lambda p: 0 if p > lim else 255)  # texto claro do HUD -> preto
    return ImageOps.expand(pb, border=20, fill=255)


def variacoes(opcoes: dict[str, Any]) -> list[tuple[str, int | None]]:
    """Lista de tentativas (modo, limiar). A primeira é a configurada."""
    t = int(opcoes.get("limiar", 140))
    brutas = [("lum", t), ("max", t), ("gray", None), ("lum", t - 35), ("max", t + 35),
              ("lum", t + 35), ("max", t - 35)]
    vistas: set = set()
    saida: list[tuple[str, int | None]] = []
    for modo, lim in brutas:
        if lim is not None:
            lim = max(30, min(240, lim))
        if (modo, lim) not in vistas:
            vistas.add((modo, lim))
            saida.append((modo, lim))
    return saida
