@echo off
REM Abre o Hub com console, mostrando os logs ao vivo
cd /d "%~dp0"
.venv\Scripts\python.exe main.py
pause
