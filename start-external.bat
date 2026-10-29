@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Novel Studio
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

rem Launcher that uses a venv OUTSIDE this project folder.
rem Why: a python that lives inside this folder may be blocked from writing the
rem library folder (outside the project), and then saving a chapter fails with
rem PermissionError. The outside venv does not have that restriction here.
rem
rem Change the default path below, or set NS_VENV before running this file:
rem   set NS_VENV=D:\somewhere\venvs\novel-studio
if not defined NS_VENV set "NS_VENV=%USERPROFILE%\venvs\novel-studio"

if not exist "%NS_VENV%\Scripts\python.exe" (
  echo [warn] external venv not found: %NS_VENV%
  echo [warn] falling back to start.bat with the project .venv.
  echo [warn] if your library is outside this folder, saving may fail.
  set "NS_VENV="
)

if defined NS_VENV echo [run] external venv: %NS_VENV%
call "%~dp0start.bat"
