@echo off
chcp 65001 >nul 2>&1
title AetherDesk Call Center Launcher
color 0A

echo.
echo ==========================================
echo   AETHERDESK CALL CENTER - STARTER
echo ==========================================
echo.

cd /d C:\Users\User\Desktop\aetherdesk_scaffold

:: Set environment (use environment variables if set, otherwise use dev defaults)
if not defined ENCRYPTION_KEY set "ENCRYPTION_KEY=REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE="
if not defined JWT_SECRET set "JWT_SECRET=dev-secret-key-change-me"
if not defined WEBSOCKET_SECRET_KEY set "WEBSOCKET_SECRET_KEY=dev-websocket-secret-change-me"
if not defined USE_POSTGRES set "USE_POSTGRES=false"
if not defined DEEPGRAM_API_KEY set "DEEPGRAM_API_KEY=your-deepgram-api-key-here"
if not defined GROQ_API_KEY set "GROQ_API_KEY=your-groq-api-key-here"
if not defined VITE_API_URL set "VITE_API_URL=http://127.0.0.1:8000"

:: Remove old DB for clean start
del /f /q aetherdesk.db 2>nul

:: START API SERVER (in own console window)
echo [1/2] Starting API Server on port 8000...
start "AetherDesk API" cmd /c "title [API] AetherDesk & color 0C & python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --log-level info & pause"

:: Wait for API
echo     Waiting for API (8 seconds)...
timeout /t 8 /nobreak >nul

:: START UI SERVER (in own console window)
echo [2/2] Starting UI Server on port 3001...
start "AetherDesk UI" cmd /c "title [UI] AetherDesk UI & color 0B & cd /d C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui & set VITE_API_URL=http://127.0.0.1:8000 & set ENCRYPTION_KEY=REDACTED_ENCRYPTION_KEY_PLEASE_ROTATE= & npx vite dev --host 127.0.0.1 --port 3001 --strictPort & pause"

echo     Waiting for UI (10 seconds)...
timeout /t 10 /nobreak >nul

echo.
echo ==========================================
echo   AETHERDESK IS RUNNING
echo ==========================================
echo.
echo   API : http://127.0.0.1:8000
echo   UI  : http://127.0.0.1:3001
echo   Docs: http://127.0.0.1:8000/docs
echo.
echo   Login: admin@aetherdesk.com / admin123
echo.
echo   Two server windows should be open above.
echo   Close this window to stop everything.
echo ==========================================
echo.

:: Open Chrome to login page
start chrome "http://127.0.0.1:3001/login"

:: Keep window open
cmd /c