AetherDesk Call Center - Build Summary
==========================================
STATUS: FULLY OPERATIONAL (Dev Mode)

What Was Built
==============

Backend API (FastAPI/Python)
- API Server: Port 8000 - apps/api/main.py
- 9 Routers: voice, voice_cloning, agent, realtime, engine, saas, protocols, campaign, auth
- Auth: /auth/login endpoint with JWT tokens
- Multi-tenant: PostgreSQL with RLS (dev: SQLite fallback)
- Fonster HTTP Client: Pure HTTP (no SDK)
- AI Stack: Deepgram STT, Chatterbox/Qwen3 TTS, Groq LLM
- HIPAA Audit Middleware + Rate Limiting + WebSocket

Frontend UI (React + Vite + Tailwind)
- UI Server: Port 3001 - agent-ui/
- 59+ routes: login, dashboard, agents, calls, campaigns, settings, voice-cloning

Infrastructure
- Kubernetes manifests (GKE, autoscaling, SSL/TLS, GPU nodes)
- Docker Compose for local dev
- Windows launcher script

Bugs Fixed During This Session
===============================
1. Missing .env file - created with all required vars
2. SQLite schema not initialized in dev mode - fixed main.py lifespan
3. Auth JWT secret mismatch (WEBSOCKET_SECRET_KEY vs JWT_SECRET) - fixed auth.py
4. Missing /auth/login endpoint - created auth router
5. Tenant INSERT 11 columns / 10 values - fixed in database.py
6. sqlite3.Row vs dict access - added _dict_factory
7. enqueue_call row[0] integer indexing - fixed to dict key
8. Health check blocking on PostgreSQL in SQLite mode - fixed
9. Vite env VITE_API_URL not passed - added to .env

API Endpoints Verified
======================
/health          200  degraded mode (dev)
/auth/login      200  returns JWT token
/api/v1/tenants  201  create tenant
/api/v1/tenants/{id}/agents  201  create agent
/api/v1/calls    201  create call
/api/v1/calls    200  get call details
/docs            200  Swagger UI

How to Start
============
Double-click: run_call_center.bat
Or run: python e2e_test.py

Login: admin@aetherdesk.com / admin123
API: http://127.0.0.1:8000
UI:  http://127.0.0.1:3001