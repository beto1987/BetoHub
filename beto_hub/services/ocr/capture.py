"""Captura de regiões da tela com mss (coordenadas físicas, em pixels reais).

O Hub roda com DPI "por monitor" (padrão do Qt 6), então as coordenadas aqui
são as mesmas que o Beto Scanner antigo salvava — por isso a importação das
áreas funciona sem conversão.

Cada thread deve ter o seu Capturador (o mss não é compartilhável entre threads).
"""

from __future__ import annotations

from typing import Any

from PIL import Image

Regiao = dict[str, int]  # {"left", "top", "width", "height"}


def regiao_valida(r: Any) -> bool:
    try:
        return int(r["width"]) >= 4 and int(r["height"]) >= 4
    except (TypeError, KeyError, ValueError):
        return False


class Capturador:
    def __init__(self):
        import mss  # import tardio: só quem captura precisa do pacote
        self._sct = mss.mss()

    def capturar(self, regiao: Regiao) -> Image.Image:
        r = {k: int(regiao[k]) for k in ("left", "top", "width", "height")}
        shot = self._sct.grab(r)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def fechar(self) -> None:
        try:
            self._sct.close()
        except Exception:
            pass

    def __enter__(self) -> "Capturador":
        return self

    def __exit__(self, *_exc) -> None:
        self.fechar()


def mudou(antes: Image.Image | None, depois: Image.Image, tolerancia: int = 25) -> bool:
    """True se a imagem mudou de forma visível (evita reprocessar a mesma tela)."""
    from PIL import ImageChops
    if antes is None or antes.size != depois.size:
        return True
    dif = ImageChops.difference(antes, depois).convert("L")
    return max(dif.getextrema()) >= tolerancia
