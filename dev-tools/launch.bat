@echo off
chcp 65001 >nul 2>&1
title AetherDesk Launcher
color 0A

setlocal

echo ============================================
echo   AetherDesk Call Center - Starting
echo ============================================
echo.

:: Set environment
set "ENCRYPTION_KEY=SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA="
set "JWT_SECRET=test-websocket-secret"
set "WEBSOCKET_SECRET_KEY=test-websocket-secret"
set "USE_POSTGRES=false"
set "DEEPGRAM_API_KEY=REPLACE_WITH_DEEPGRAM_API_KEY"
set "GROQ_API_KEY=REPLACE_WITH_GROQ_API_KEY"
set "VITE_API_URL=http://127.0.0.1:8000"

:: Kill old
echo [1/4] Cleaning old processes...
taskkill /F /IM "node.exe" 2>nul
timeout /t 2 /nobreak >nul

cd /d C:\Users\User\Desktop\aetherdesk_scaffold

:: Delete old SQLite DB for clean start
del /f /q aetherdesk.db 2>nul

:: Start API server in new console window
echo [2/4] Starting API Server on port 8000...
start "AetherDesk API Server" cmd /c "title API Server ^& color 0C ^& python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --log-level info ^& pause"

:: Wait for API
echo [3/4] Waiting for API startup (10s)...
timeout /t 10 /nobreak >nul

:: Start UI server in new console window
echo [4/4] Starting UI Server on port 3001...
start "AetherDesk UI Server" cmd /c "title UI Server ^& color 0B ^& cd /d C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui ^& set VITE_API_URL=http://127.0.0.1:8000 ^& set ENCRYPTION_KEY=SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA= ^& npx vite dev --host 127.0.0.1 --port 3001 --strictPort ^& pause"

echo.
echo Waiting for UI startup (8s)...
timeout /t 8 /nobreak >nul

echo.
echo ============================================
echo   AETHERDESK CALL CENTER IS RUNNING
echo ============================================
echo.
echo   API Server : http://127.0.0.1:8000
echo   UI Server  : http://127.0.0.1:3001
echo   API Docs   : http://127.0.0.1:8000/docs
echo.
echo   Login: admin@aetherdesk.com / admin123
echo.
echo ============================================
echo.
echo   Opening Chrome browser...
echo.

:: Open Chrome
start chrome "http://127.0.0.1:3001/login"

:: Keep window open
cmd /c