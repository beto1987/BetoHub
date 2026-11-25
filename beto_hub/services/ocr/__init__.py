"""OCR compartilhado (extraído do Star Citizen Beto Scanner).

- engine.py ....... motor de OCR (OCR do Windows via winocr, ou Tesseract)
- preprocess.py ... preparo da imagem (ampliar, contraste, binarizar) e variações
- capture.py ...... captura de uma região da tela (mss)
- janela.py ....... descobre se o Star Citizen está em primeiro plano

Tudo aqui só LÊ a tela. Nada toca no processo ou nos arquivos do jogo.
"""

from .engine import ErroOCR, MotorOCR
from .preprocess import preprocessar, variacoes

__all__ = ["ErroOCR", "MotorOCR", "preprocessar", "variacoes"]
