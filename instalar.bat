@echo off
REM Cria o ambiente virtual .venv e instala as dependencias
cd /d "%~dp0"
py -3.13 -m venv .venv || goto erro
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto erro
echo.
echo Pronto! Use iniciar.bat para abrir o Hub.
pause
exit /b 0
:erro
echo.
echo Algo deu errado. Confira se o Python 3.13 esta instalado (comando: py -3.13 --version).
pause
exit /b 1
