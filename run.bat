@echo off
setlocal
title MIAP
echo Starting MIAP backend and frontend...
start "MIAP backend" cmd /k "%~dp0backend.bat"
start "MIAP frontend" cmd /k "%~dp0frontend.bat"
timeout /t 4 /nobreak >nul
start "" http://localhost:5173
endlocal
