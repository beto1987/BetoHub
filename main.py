"""Ponto de entrada do Star Citizen Beto Hub.

    python main.py      (com console, mostra os logs)
    pythonw main.py     (sem console)
"""

import sys
from pathlib import Path

# Garante que beto_hub/ e plugins/ sejam importáveis mesmo rodando de outra pasta.
sys.path.insert(0, str(Path(__file__).resolve().parent))

if sys.platform == "win32":
    import ctypes

    try:
        # Faz o Windows tratar o Hub como app próprio (ícone certo na barra de tarefas).
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Beto.StarCitizenBetoHub")
    except (AttributeError, OSError):
        pass

from beto_hub.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
