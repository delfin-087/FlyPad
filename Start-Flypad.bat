@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Bitte DISCORD_TOKEN in der Datei .env eintragen und erneut starten.
    notepad ".env"
    pause
    exit /b 0
)
".venv\Scripts\python.exe" bot.py
pause
exit /b 0
:fail
echo Start fehlgeschlagen. Bitte Python 3.12 oder neuer und Internetverbindung pruefen.
pause
exit /b 1
