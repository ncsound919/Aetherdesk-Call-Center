@echo off
title AetherDesk Call Center Setup
color 0A

echo ============================================
echo   AetherDesk Call Center - Starting
echo ============================================
echo.

:: Kill any existing processes
echo Cleaning up old processes...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM node.exe 2>nul
timeout /t 2 /nobreak >nul

:: Set environment variables
set ENCRYPTION_KEY=REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE=
set WEBSOCKET_SECRET_KEY=test-websocket-secret

cd /d C:\Users\User\Desktop\aetherdesk_scaffold

echo.
echo [1/3] Starting API Server on port 8000...
start "API Server" cmd /c "title API Server ^& color 0C ^& python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000"

timeout /t 8 /nobreak >nul

echo.
echo [2/3] Starting UI Server on port 3001...
cd /d C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui
start "UI Server" cmd /c "title UI Server ^& color 0B ^& set ENCRYPTION_KEY=REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE= && set WEBSOCKET_SECRET_KEY=test-websocket-secret && npx vite --host 127.0.0.1 --port 3001"

timeout /t 8 /nobreak >nul

echo.
echo [3/3] Opening Chrome browser...
start chrome "http://127.0.0.1:3001/"

echo.
echo ============================================
echo   All started! Give it 10 seconds to load.
echo ============================================
echo.
echo   API  : http://127.0.0.1:8000
echo   UI   : http://127.0.0.1:3001
echo   Docs : http://127.0.0.1:8000/docs
echo.
echo   Close this window to stop all servers.
echo   Keep API and UI windows open.
echo ============================================

:: Keep this window open
cmd /c