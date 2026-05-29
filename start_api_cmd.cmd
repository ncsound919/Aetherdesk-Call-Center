@echo off
chcp 65001 >nul 2>&1
title AetherDesk API Server
color 0C

cd /d C:\Users\User\Desktop\aetherdesk_scaffold

set ENCRYPTION_KEY=SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA=
set JWT_SECRET=test-websocket-secret
set WEBSOCKET_SECRET_KEY=test-websocket-secret
set USE_POSTGRES=false
set DEEPGRAM_API_KEY=REPLACE_WITH_DEEPGRAM_API_KEY
set GROQ_API_KEY=REPLACE_WITH_GROQ_API_KEY

echo Starting AetherDesk API Server...
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --log-level info
echo Server exited with errorlevel %errorlevel%
pause