"""Motor de OCR: OCR do Windows (winocr) com Tesseract como alternativa.

Mesma lógica do Beto Scanner: tenta "auto" -> Windows -> Tesseract; descobre
sozinho um idioma do OCR do Windows que funcione (en-US, en, pt-BR...).

Cada thread deve criar o seu MotorOCR (o winocr usa um event loop asyncio próprio).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from beto_hub.core.i18n import tr
from ...core.logging_setup import obter_logger

log = obter_logger("ocr")

Palavra = tuple[str, float, float, float, float]  # (texto, x, y, largura, altura)


class ErroOCR(RuntimeError):
    pass


def _g(o: Any, k: str, padrao: Any = None) -> Any:
    """Lê atributo de objeto winrt ou chave de dicionário."""
    if isinstance(o, dict):
        return o.get(k, padrao)
    return getattr(o, k, padrao)


class MotorOCR:
    def __init__(self, motor: str = "auto", idioma: str = "auto",
                 tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
        self.preferencia_idioma = idioma or "auto"
        self.motor: str | None = None
        self.idioma: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        erros: list[str] = []

        if motor in ("auto", "windows"):
            try:
                import winocr  # noqa: F401
                self._winocr = winocr
                self._loop = asyncio.new_event_loop()
                self.motor = "windows"
            except Exception as e:  # pacote ausente, Windows sem OCR...
                erros.append(tr("OCR do Windows (winocr): {erro}", erro=e))

        if self.motor is None and motor in ("auto", "tesseract"):
            try:
                import pytesseract
                if tesseract_cmd and os.path.exists(tesseract_cmd):
                    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
                pytesseract.get_tesseract_version()
                self._pytesseract = pytesseract
                self.motor = "tesseract"
            except Exception as e:
                erros.append(f"Tesseract: {e}")

        if self.motor is None:
            raise ErroOCR(
                tr("Nenhum OCR disponível.") + "\n  " + "\n  ".join(erros)
                + "\n" + tr("Rode 'pip install winocr' (recomendado) ou instale o Tesseract.")
            )
        log.info("Motor de OCR: %s", self.motor)

    # ------------------------------------------------------------ Windows
    def _idiomas(self) -> list[str]:
        if self.idioma:
            return [self.idioma]
        if self.preferencia_idioma != "auto":
            return [self.preferencia_idioma]
        return ["en-US", "en", "pt-BR", "pt", "en-GB"]

    def _reconhecer_windows(self, img):
        ultimo: Exception | None = None
        for idioma in self._idiomas():
            try:
                res = self._loop.run_until_complete(self._winocr.recognize_pil(img, idioma))
                if self.idioma != idioma:
                    log.info("OCR do Windows usando o idioma %s", idioma)
                self.idioma = idioma
                return res
            except Exception as e:
                ultimo = e
        raise ErroOCR(
            tr("OCR do Windows falhou ({erro}). Instale o pacote de idioma Inglês no Windows "
               "ou escolha o idioma do OCR nas opções da Mineração.", erro=ultimo)
        )

    # ------------------------------------------------------------ API
    def ler(self, img) -> str:
        """Texto da imagem (já pré-processada)."""
        if self.motor == "windows":
            res = self._reconhecer_windows(img)
            if hasattr(res, "text"):
                return res.text or ""
            if isinstance(res, dict):
                return res.get("text", "")
            return str(res)
        return self._pytesseract.image_to_string(
            img, config="--psm 6 -c tessedit_char_whitelist=0123456789,."
        )

    def ler_palavras(self, img) -> tuple[str, list[Palavra]]:
        """Texto + palavras com posição (para ler painéis com rótulo e valor)."""
        if self.motor == "windows":
            try:
                res = self._reconhecer_windows(img)
            except ErroOCR:
                return "", []
            palavras: list[Palavra] = []
            for linha in (_g(res, "lines") or []):
                for p in (_g(linha, "words") or []):
                    r = _g(p, "bounding_rect") or {}
                    palavras.append((_g(p, "text") or "", float(_g(r, "x", 0)), float(_g(r, "y", 0)),
                                     float(_g(r, "width", 0)), float(_g(r, "height", 0))))
            return (_g(res, "text") or ""), palavras
        t = self._pytesseract
        d = t.image_to_data(img, output_type=t.Output.DICT, config="--psm 6")
        palavras = [(d["text"][i], d["left"][i], d["top"][i], d["width"][i], d["height"][i])
                    for i in range(len(d["text"])) if str(d["text"][i]).strip()]
        return " ".join(p[0] for p in palavras), palavras

    def fechar(self) -> None:
        if self._loop is not None:
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None
