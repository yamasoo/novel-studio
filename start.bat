@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 小說工作台

if not exist ".venv\Scripts\python.exe" (
  echo 第一次啟動：建立 Python 虛擬環境……
  where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
  if not exist ".venv\Scripts\python.exe" (
    echo 找不到 Python。請先安裝 Python 3.9 以上：https://www.python.org/downloads/
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
)

rem requirements.txt 有變動（例如更新了工作台）就重新安裝套件
fc /b requirements.txt ".venv\requirements.installed" >nul 2>nul
if errorlevel 1 (
  echo 安裝／更新套件……
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo 套件安裝失敗，請檢查網路後再試一次。
    pause
    exit /b 1
  )
  copy /y requirements.txt ".venv\requirements.installed" >nul
)

".venv\Scripts\python.exe" app.py
pause
