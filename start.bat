@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 小說工作台

rem 預設用專案裡的 .venv。若這個專案放在會被限制寫入的位置（例如被某個沙箱工具接管的工作區），
rem 可以把虛擬環境放外面，用環境變數 NS_VENV 指過去：
rem   set NS_VENV=C:\Users\你\venvs\novel-studio
if defined NS_VENV (
  set "VENV=%NS_VENV%"
) else (
  set "VENV=%~dp0.venv"
)

if not exist "%VENV%\Scripts\python.exe" (
  echo 第一次啟動：建立 Python 虛擬環境（%VENV%）……
  where py >nul 2>nul && (py -3 -m venv "%VENV%") || (python -m venv "%VENV%")
  if not exist "%VENV%\Scripts\python.exe" (
    echo 找不到 Python。請先安裝 Python 3.9 以上：https://www.python.org/downloads/
    pause
    exit /b 1
  )
  "%VENV%\Scripts\python.exe" -m pip install --upgrade pip >nul
)

rem requirements.txt 有變動（例如更新了工作台）就重新安裝套件
set "STAMP=%VENV%\requirements.installed"
fc /b requirements.txt "%STAMP%" >nul 2>nul
if errorlevel 1 (
  echo 安裝／更新套件……
  "%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo 套件安裝失敗，請檢查網路後再試一次。
    pause
    exit /b 1
  )
  copy /y requirements.txt "%STAMP%" >nul
)

"%VENV%\Scripts\python.exe" app.py
pause
