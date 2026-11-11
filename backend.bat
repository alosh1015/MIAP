@echo off
setlocal
title MIAP backend
cd /d "%~dp0backend"

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Python environment not found at .venv\Scripts\python.exe
  echo Create it with:
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r backend\requirements.txt
  pause
  exit /b 1
)

echo Starting MIAP backend on http://127.0.0.1:8000
"%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
if errorlevel 1 pause
endlocal
