set ENCRYPTION_KEY=SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA=
set WEBSOCKET_SECRET_KEY=test-websocket-secret

cd /d C:\Users\User\Desktop\aetherdesk_scaffold

echo Starting API server...
start "" python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

echo Starting UI server...
cd /d C:\Users\User\Desktop\aetherdesk_scaffold\agent-ui
start "" npm run dev -- --host 127.0.0.1 --port 3001

echo Servers started!
echo API: http://127.0.0.1:8000
echo UI: http://127.0.0.1:3001
echo.
echo Press Ctrl+C in this window to stop.

REM Keep this window open
cmd /c pause >nul