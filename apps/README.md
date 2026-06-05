# `apps/` — Application Modules

This directory contains the core application code for AetherDesk. Each subdirectory
is a self-contained service or module.

## Structure

```
apps/
├── api/          # FastAPI backend — REST + WebSocket endpoints, AI pipeline,
│                 # voice routing, session management, multi-tenant auth
├── voice/        # Fonoster voice server — handles inbound SIP/telephony,
│                 # bridges to the AI pipeline via WebSocket
└── worker/       # Celery background workers — async campaign dialing,
                  # RAG indexing, webhook delivery
```

## Key Entry Points

| Component | Start command | Description |
|---|---|---|
| API server | `make api` | FastAPI on port 8000 |
| Full stack | `make dev` | Docker Compose (API + UI + DB + Redis) |
| Workers | `celery -A apps.worker worker -l info` | Background tasks |

## Development Notes

- All environment variables must be set via `.env` (copy from `.env.example`).
- Database migrations are managed with Alembic — see `make db-migrate`.
- Never run `make db-reset` against a production or shared staging database.
