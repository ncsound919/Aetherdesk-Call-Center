# AetherDesk Call Center Platform

A privacy-focused, cost-efficient digital call center SaaS platform built with Fonoster and FreeSWITCH as alternatives to Twilio. Self-hosted on Google Cloud with HIPAA/GDPR compliance.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Agent UI (React)                      │
│  Dashboard | Agent Mgmt | Call Logs | Settings          │
└─────────────────┬───────────────────────────────────────┘
                  │ REST API + WebSocket
┌─────────────────▼───────────────────────────────────────┐
│              API Gateway (FastAPI)                       │
│  Tenant Mgmt | Agent Mgmt | Call Control | Billing      │
└──────┬──────────┬──────────┬──────────────┬─────────────┘
       │          │          │              │
┌──────▼──┐  ┌───▼────┐  ┌──▼────────┐  ┌──▼──────────┐
│PostgreSQL│  │  Redis  │  │ Fonoster  │  │  FreeSWITCH  │
│ (DB)     │  │ (Cache) │  │(Voice API)│  │ (SIP/RTP)   │
└──────────┘  └─────────┘  └───────────┘  └─────────────┘
       │                                       │
       │              ┌───────────────────────▼──┐
       │              │   Google Cloud / GKE     │
       │              │   - HIPAA/GDPR Compliant │
       │              │   - Encrypted Storage    │
       │              │   - Regional: us-east1   │
       │              └─────────────────────────┘
```

## Key Features

- **Agent Rental System**: Rent AI/human agents by hour, day, week, or month
- **Smart Call Routing**: AI-powered intent detection and agent matching
- **Multi-Tenant Isolation**: Row-Level Security in PostgreSQL ensures data separation
- **HIPAA/GDPR Compliant**: Encryption at rest, audit logs, data residency controls
- **Real-Time Dashboard**: Live agent status, call monitoring, analytics
- **Fonoster Voice API**: Modern voice application development (TwiML-compatible)
- **FreeSWITCH Media Server**: Open-source SIP/RTP handling

## Quick Start

### Prerequisites
- Google Cloud SDK installed and authenticated
- Docker and Docker Compose
- kubectl configured for your GKE cluster

### 1. Set Environment Variables
```bash
cp .env.example .env
# Edit .env with your actual values
```

### 2. Local Development (Docker)
```bash
docker-compose up -d
```

### 3. Production Deployment (GKE)
```bash
# Set your environment variables first
export DB_PASSWORD="your-secure-password"
export REDIS_PASSWORD="your-redis-password"
# ... other variables

# Run deployment
chmod +x scripts/deploy.sh
./scripts/deploy.sh production
```

### 4. Access the Platform
- **API**: http://localhost:3000 (local) or your GKE LoadBalancer IP
- **Agent UI**: http://localhost:3001 (local)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/tenants` | POST/GET | Tenant management |
| `/api/v1/tenants/{id}/agents` | POST/GET | Agent management |
| `/api/v1/agents/{id}/status` | PATCH | Update agent status |
| `/api/v1/calls` | POST/GET | Create/list calls |
| `/api/v1/calls/{id}/action` | POST | Call actions (answer, hangup, transfer) |
| `/api/v1/recordings/{id}` | GET | Access recordings (HIPAA-logged) |
| `/api/v1/usage` | GET | Usage analytics |
| `/api/v1/billing` | GET | Billing summary |
| `/ws/calls/{tenantId}` | WS | Real-time call updates |
| `/ws/agent/{agentId}` | WS | Agent call assignments |

## Compliance

- **HIPAA**: AES-256 encryption at rest, TLS in transit, audit logging, PII redaction
- **GDPR**: Data residency (US-East1), right to deletion, consent management
- **SOC 2**: Network policies, RBAC, access controls

## Cost Comparison: Twilio vs. Fonoster/FreeSWITCH

| Feature | Twilio | Fonoster + FreeSWITCH |
|---------|--------|----------------------|
| Per-minute voice | $0.0085+ | SIP trunk cost only |
| Phone numbers | $1.15+/month | Port your own or SIP trunk |
| Recording | $0.0025/min | Free (self-hosted storage) |
| Transcription | $0.01/min | Deepgram/whisper (configurable) |
| TTS | Free (self-hosted) | Chatterbox/OpenAI (configurable) |
| Monthly platform | ~$50-200+ | Infrastructure only |
| Privacy | Third-party | Full control, self-hosted |

## Project Structure

```
aetherdesk_scaffold/
├── apps/
│   ├── api/                    # FastAPI SaaS platform
│   │   ├── main.py
│   │   ├── Dockerfile
│   │   └── routers/
│   └── voice/                  # Fonoster voice application
│       └── server.js
├── agent-ui/                   # React agent dashboard
│   ├── src/
│   └── package.json
├── config/
│   ├── database/
│   │   └── schema.sql
│   ├── freeswitch/
│   │   └── sip_profiles.xml
│   └── protocols/
├── kubernetes/
│   ├── deployment.yml
│   └── namespace.yaml
├── scripts/
│   └── deploy.sh
├── tests/
│   └── e2e/
├── .env.example
├── docker-compose.yml
└── README.md
```