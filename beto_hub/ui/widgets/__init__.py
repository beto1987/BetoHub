"""Widgets reutilizáveis pelos módulos."""

from .campos import instalar_dicas_discretas
from .key_capture import CampoAtalho
from .paineis import PainelEmConstrucao, PainelErroPlugin

__all__ = ["CampoAtalho", "PainelEmConstrucao", "PainelErroPlugin", "instalar_dicas_discretas"]
