@echo off
REM Xpns launcher: runs the command-line entry point with the project's venv.
REM Double-click it, or use a desktop shortcut pointing to it.
REM Arguments are passed on to cli.main, e.g.: xpns.bat --headed

REM Work from the folder of this script, wherever the project is located,
REM so that .env, data\ and logs\ are found.
cd /d "%~dp0"

REM UTF-8 console, so that accents display correctly.
chcp 65001 > nul
set PYTHONUTF8=1

if not exist "venv\Scripts\python.exe" (
    echo Environnement Python introuvable : %~dp0venv
    echo.
    echo Pour l'installer, ouvrir une invite de commandes et taper :
    echo.
    echo   cd /d "%~dp0"
    echo   python -m venv venv
    echo   venv\Scripts\python.exe -m pip install -r requirements.txt
    echo   venv\Scripts\python.exe -m playwright install chromium
    echo.
    echo Puis copier .env.example en .env et y saisir les identifiants Louty.
    pause
    exit /b 1
)

"venv\Scripts\python.exe" -m cli.main %*

REM Keep the window open to read the result.
pause
