@echo off
rem ═══════════════════════════════════════════════════════════════
rem  Umi starten (per Doppelklick)
rem  Nutzt die mit "Umi_Installieren.bat" angelegte Umgebung.
rem ═══════════════════════════════════════════════════════════════
title Umi - Dein persoenlicher KI-Assistent

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe "%~dp0umi_assistent.py" %*
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo  [FEHLER] Python wurde nicht gefunden.
        echo           Bitte zuerst "Umi_Installieren.bat" ausfuehren.
        pause
        exit /b 1
    )
    python "%~dp0umi_assistent.py" %*
)

if errorlevel 1 (
    echo.
    echo  Umi wurde mit einem Fehler beendet. Bitte Fensterinhalt pruefen.
    pause
)
