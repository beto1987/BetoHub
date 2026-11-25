@echo off
REM Abre o Hub sem janela de console
cd /d "%~dp0"
start "" .venv\Scripts\pythonw.exe main.py
