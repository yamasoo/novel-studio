@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Novel Studio
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

rem NOTE: keep this file UTF-8 (no BOM) with CRLF line endings.
rem ASCII-only comments: non-ASCII remarks get split by cmd in some code pages.
rem
rem Which virtualenv:
rem   default  = .venv inside this folder
rem   override = set NS_VENV to a venv outside the project folder, e.g.
rem              set NS_VENV=C:\Users\you\venvs\novel-studio
rem   Use the outside one when the project folder is managed by a sandbox tool:
rem   a python that lives inside the workspace may not be allowed to write the
rem   library folder, and saving chapters then fails with PermissionError.
if defined NS_VENV (
  set "VENV=%NS_VENV%"
) else (
  set "VENV=%~dp0.venv"
)

if not exist "%VENV%\Scripts\python.exe" (
  echo [setup] creating virtualenv: %VENV%
  where py >nul 2>nul && (py -3 -m venv "%VENV%") || (python -m venv "%VENV%")
  if not exist "%VENV%\Scripts\python.exe" (
    echo Python not found. Install Python 3.9+ first: https://www.python.org/downloads/
    pause
    exit /b 1
  )
  "%VENV%\Scripts\python.exe" -m pip install --upgrade pip >nul
)

rem Reinstall packages when requirements.txt changed.
set "STAMP=%VENV%\requirements.installed"
fc /b requirements.txt "%STAMP%" >nul 2>nul
if errorlevel 1 (
  echo [setup] installing requirements...
  "%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Package install failed. Check your network and try again.
    pause
    exit /b 1
  )
  copy /y requirements.txt "%STAMP%" >nul
)

echo [run] venv: %VENV%
"%VENV%\Scripts\python.exe" app.py
pause
