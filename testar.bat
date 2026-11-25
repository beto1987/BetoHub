@echo off
REM Roda os testes automaticos
cd /d "%~dp0"
.venv\Scripts\python.exe -m pytest -v tests
pause
