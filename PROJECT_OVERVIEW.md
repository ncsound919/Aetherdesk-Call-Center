# AetherDesk Call Center Platform - Final Project Structure Overview

## Core Application Files
apps/api/                    # FastAPI SaaS Platform
  ├── main.py               # Main API application & endpoints
  ├── fonoster_client.py    # Fonoster HTTP client adapter  
  ├── websocket_server.py   # Real-time WebSocket server
  ├── Dockerfile            # Container configuration
  ├── requirements.txt      # Python dependencies
  └── routers/              # API route handlers
apps/voice/                  # Fonoster Voice Application
  └── server.js             # Core call handling & routing logic

## Frontend - Agent Dashboard
agent-ui/
  ├── src/
  │   ├── App.jsx           # Main React application
  │   ├── main.jsx          # Entry point
  │   ├── index.css         # Global styles
  │   ├── pages/            # Route components
  │   │   ├── Dashboard.jsx
  │   │   ├── AgentManagement.jsx
  │   │   ├── CallLogs.jsx
  │   │   ├── Login.jsx
  │   │   └── Settings.jsx
  │   ├── components/       # Shared UI components
  │   │   ├── Sidebar.jsx
  │   │   ├── StatCard.jsx
  │   │   ├── AgentStatusChart.jsx
  │   │   ├── CallVolumeChart.jsx
  │   │   └── RecentCalls.jsx
  │   ├── context/          # React state management
  │   │   ├── AuthContext.jsx
  │   │   └── SocketContext.jsx
  │   └── services/         # API client
  │       └── api.js
  ├── Dockerfile            # Container configuration
  ├── nginx.conf            # Reverse proxy config
  ├── package.json          # NPM dependencies
  ├── tailwind.config.js    # CSS framework config
  └── vite.config.js        # Build tool config

## Infrastructure Configuration
config/
  ├── database/
  │   └── schema.sql        # PostgreSQL schema (HIPAA/GDPR compliant)
  ├── fonoster/
  │   └── config.json       # Fonoster Voice Server configuration
  ├── freeswitch/
  │   └── sip_profiles.xml  # FreeSWITCH SIP configuration
  └── protocols/            # Call flow protocols
      ├── flow.json
      ├── triage_v1.json
      ├── sales_flow.json
      ├── cs_flow.json
      └── ...

## Kubernetes Deployments
kubernetes/
  ├── deployment.yml        # Main deployment manifests
  ├── services.yml          # Service definitions
  ├── namespace.yaml        # Kubernetes namespace
  ├── configmap.yml         # Centralized configuration
  ├── monitoring.yml        # Prometheus/Grafana monitoring
  ├── backup.yml            # Automated backup configuration
  └── ssl.yml               # TLS/SSL configuration

## CI/CD
.github/workflows/
  └── ci-cd.yml             # GitHub Actions pipeline

## Scripts
scripts/
  ├── deploy.sh             # Production deployment script
  └── automate_outreach.py  # Outreach automation

## Tests
tests/
  ├── e2e/                  # End-to-end tests (Playwright)
  │   ├── gcloud_console_setup_test.py
  │   ├── gke_cluster_setup_test.py
  │   ├── gcloud_setup_test.py
  │   ├── test_functional.py
  │   └── ...
  ├── test_app.py           # Application tests
  ├── test_e2e.py           # E2E test suite
  ├── test_verification.py  # Infrastructure verification
  └── stress_test.py        # Load testing

## Documentation
README.md                   # Complete project documentation
.env.example                # Environment variable template
.docker-compose.yml         # Local development setup

## Compliance & Security Features
✅ PostgreSQL Row-Level Security (RLS) - Tenant isolation
✅ AES-256-GCM encryption at rest for all sensitive data
✅ TLS 1.3 for all data in transit
✅ HIPAA-compliant audit logging
✅ GDPR consent management & data deletion
✅ Automatic call recording retention (365 days)
✅ PII redaction in transcripts
✅ SOC 2-aligned access controls
✅ Automated encrypted backups to GCS