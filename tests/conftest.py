"""Coloca a raiz do projeto no sys.path para os testes acharem beto_hub/ e fixa o idioma em português."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beto_hub.core import i18n  # noqa: E402

i18n.definir_idioma("pt-BR")  # os testes comparam textos em português, seja qual for o idioma do seu Hub
