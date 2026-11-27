# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller para o StarHub (modo pasta, sem UPX).

Rode pelo compilar.ps1. Gera dist/StarHub/ com StarHub.exe e a pasta _internal/.

- Modo pasta (onedir), não arquivo único: o .exe de arquivo único se extrai numa pasta
  temporária a cada abertura, um padrão que antivírus confundem com malware.
- Sem UPX: compressão de executável também gera falsos positivos.
- Os módulos (plugins/) vão como arquivos: o Hub os descobre pela pasta e os importa em
  tempo de execução, então as bibliotecas que eles usam entram como hiddenimports.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

RAIZ = Path(SPECPATH).parent  # noqa: F821 (SPECPATH é definido pelo PyInstaller)
IGNORAR = {"__pycache__", ".pytest_cache"}


def arquivos(pasta: str, destino: str | None = None) -> list[tuple[str, str]]:
    """Todos os arquivos de uma pasta (sem __pycache__), preservando as subpastas."""
    base = RAIZ / pasta
    saida = []
    for arq in base.rglob("*"):
        if arq.is_file() and not IGNORAR & set(arq.relative_to(base).parts) and arq.suffix != ".pyc":
            saida.append((str(arq), str(Path(destino or pasta) / arq.relative_to(base).parent)))
    return saida


datas = arquivos("plugins") + arquivos("beto_hub/ui/theme") + arquivos("beto_hub/i18n")

hiddenimports = (
    collect_submodules("beto_hub")
    + collect_submodules("winrt")  # OCR do Windows (winocr)
    + collect_submodules("PIL")
    + ["winocr", "mss", "mss.windows", "mss.windows.gdi", "tomlkit",
       # biblioteca padrão usada só pelos módulos (que não são analisados pelo PyInstaller)
       "csv", "statistics", "winsound", "unicodedata", "html", "copy", "math", "concurrent.futures"]
)

a = Analysis(  # noqa: F821
    [str(RAIZ / "main.py")],
    pathex=[str(RAIZ)],
    binaries=collect_dynamic_libs("winrt"),
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "_pytest", "pyinstaller", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StarHub",
    console=False,
    icon=str(RAIZ / "beto_hub" / "ui" / "theme" / "icone.ico"),
    version=str(RAIZ / "instalador" / "versao_exe.txt"),
    upx=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    upx=False,
    name="StarHub",
)
