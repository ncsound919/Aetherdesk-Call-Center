@echo off
chcp 65001 >nul 2>&1
title AetherDesk Call Center - Starting
color 0A

echo ============================================
echo   AetherDesk Call Center Setup
echo ============================================
echo.

:: Kill old processes
echo [1/5] Cleaning old processes...
taskkill /F /IM "python.exe" 2>nul
taskkill /F /IM "node.exe" 2>nul
taskkill /F /IM "chrome.exe" 2>nul
timeout /t 2 /nobreak >nul

:: Set environment
set ENCRYPTION_KEY=REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE=
set WEBSOCKET_SECRET_KEY=test-websocket-secret

cd /d C:\Users\User\Desktop\aetherdesk_scaffold

:: Start API server in background window
echo [2/5] Starting API Server on port 8000...
start "AetherDesk API Server" /min cmd /c "title API Server ^& color 0C ^& python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 2>&1"

:: Wait for API
echo [3/5] Waiting for API to start...
timeout /t 8 /nobreak >nul

:: Start UI server in background window
echo [4/5] Starting UI Server on port 3001...
cd /d C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui
start "AetherDesk UI Server" /min cmd /c "title UI Server ^& color 0B ^& set ENCRYPTION_KEY=REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE= ^&^& set WEBSOCKET_SECRET_KEY=test-websocket-secret ^&^& npm run dev -- --host 127.0.0.1 --port 3001 2>&1"

:: Wait for UI
echo [5/5] Waiting for UI to start...
timeout /t 10 /nobreak >nul

:: Open Chrome
echo.
echo Opening Chrome browser...
echo.
start chrome "http://127.0.0.1:3001/"
timeout /t 3 /nobreak >nul

echo ============================================
echo   SUCCESS! Call Center is running:
echo ============================================
echo.
echo   API Server : http://127.0.0.1:8000
echo   UI Server  : http://127.0.0.1:3001
echo   API Docs   : http://127.0.0.1:8000/docs
echo.
echo   If Chrome shows an error, wait 5sec then refresh.
echo   Keep the two server windows open!
echo.
echo   Close this window to stop all servers.
echo ============================================

:: Keep this main window open
cmd /c