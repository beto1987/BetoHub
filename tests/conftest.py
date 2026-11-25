"""Coloca a raiz do projeto no sys.path para os testes acharem beto_hub/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
