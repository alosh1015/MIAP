@echo off
setlocal
title MIAP frontend
cd /d "%~dp0frontend"

if not exist node_modules (
  echo Installing frontend dependencies...
  call npm install
  if errorlevel 1 (
    pause
    exit /b 1
  )
)

echo Starting MIAP frontend on http://localhost:5173
call npm run dev -- --port 5173
if errorlevel 1 pause
endlocal
