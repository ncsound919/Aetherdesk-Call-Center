# Aetherdesk — SaaS Deployment Guide

Aetherdesk is a **product you deploy per customer** — not your personal copy. Each
deployment gets its own isolated stack (own DB, own voice, own domain).

## Prerequisites
- Docker + Docker Compose v2 on a server (Linux VM, 8GB+ RAM, 4+ CPU).
- A domain pointing at the server (for TLS).
- Keys: Deepgram (STT), Fonoster, optional Stripe (billing).

## Deploy (one command)
```bash
cp .env.saas.example .env
# edit .env: PUBLIC_DOMAIN, DB_PASSWORD, REDIS_PASSWORD, API keys
docker compose -f docker-compose.saas.yml up -d --build
```
Caddy terminates TLS automatically. Health: `curl https://<domain>/health`.

## The stack
| Service | Role |
|---|---|
| proxy (Caddy) | TLS + routing |
| api-gateway | Core API (uvicorn :8000) |
| celery-worker / -beat | Async calls, transcriptions, billing |
| db (Postgres 15) / redis | Data + queue |
| fonoster | Telephony (SIP + gRPC :50051) |
| chatterbox | Self-hosted TTS (privacy) |

## Multi-tenant model
- **Per-deployment isolation** is the default: each customer gets a full stack.
- `TENANT_MODE=multi` supports tenants within one stack (organization-scoped
  recordings, agents, numbers). Choose per deal size.
- Every call is recorded → **recordings/** volume; retention + consent flags are
  tenant-configurable.

## Compliance (mandatory for call-center SaaS)
- **Consent**: recording-consent capture on every inbound call; flag in the
  transcript/recording metadata.
- **Retention**: set per-tenant recording retention; purge on contract end.
- **Guardian gate**: the Overlay365 Guardian reviews call-handling content
  (scripts, disclosures) before deploy.
- **Data residency**: Postgres + recordings stay on the customer's server; no
  third-party call audio.

## Billing
- `BILLING_PROVIDER=stripe` + `STRIPE_SECRET_KEY` enables per-tenant subscription
  hooks (seats, minutes). Leave `none` for pilots.
- Revenue: $100–300/site/mo target → 10 deployments = $1–3k/mo run-rate (mission E2).

## Operations
- **Backups**: `docker run --rm -v aetherdesk_db-data:/data -v $(pwd):/backup alpine tar czf /backup/db-$(date +%F).tar.gz -C /data .`
- **Updates**: `docker compose -f docker-compose.saas.yml pull && up -d --build`
- **Health**: `GET /health` returns API + DB + Redis + Fonoster status.
- **Rollback**: image tags are pinned in the compose; re-pin to previous digest.

## Promoting to production SaaS
1. Bake a **multi-tenant onboarding flow** (create org → provision number → invite agents).
2. Add **usage metering** per tenant (minutes, seats) → billing webhook.
3. Wire the **Self-Repair** cron to this stack's `/health` for auto-restarts.
4. Ship the **Aetherdesk agent** (Draymond) as the deployment's control plane.
