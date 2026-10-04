@echo off
rem ═══════════════════════════════════════════════════════════════
rem  Umi - Installation (nur einmal ausfuehren)
rem  Erstellt eine virtuelle Python-Umgebung und installiert
rem  alle Bibliotheken. Danach Umi ueber "Umi_Starten.bat" nutzen.
rem ═══════════════════════════════════════════════════════════════
title Umi - Installation
echo.
echo  ==============================================================
echo    Umi - Installation (einmalig ausfuehren)
echo  ==============================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo  [FEHLER] Python wurde nicht gefunden.
    echo           Bitte Python 3.13 von https://www.python.org/downloads/
    echo           installieren und dabei "Add python.exe to PATH" anhaken.
    echo.
    pause
    exit /b 1
)

if not exist .venv (
    echo  [1/3] Erstelle Python-Umgebung (.venv) ...
    py -3.13 -m venv .venv 2>nul || py -3 -m venv .venv
) else (
    echo  [1/3] Python-Umgebung (.venv) bereits vorhanden.
)

if not exist .venv\Scripts\python.exe (
    echo  [FEHLER] Die Python-Umgebung konnte nicht erstellt werden.
    pause
    exit /b 1
)

echo  [2/3] Aktualisiere pip ...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet

echo  [3/3] Installiere Bibliotheken (dauert beim ersten Mal einige Minuten) ...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [FEHLER] Installation fehlgeschlagen. Bitte Internetverbindung pruefen
    echo           und den Befehl erneut ausfuehren.
    pause
    exit /b 1
)

echo.
echo  ==============================================================
echo    [OK] Installation abgeschlossen!
echo    Starte Umi per Doppelklick auf  Umi_Starten.bat
echo  ==============================================================
echo.
pause
