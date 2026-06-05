# `config/` — Runtime Configuration

This directory contains environment-specific configuration files, feature flag
definitions, and service configuration templates.

## ⚠️ Security Rules

- **Never commit real secrets** to this directory or anywhere in the repo.
- All secrets must be injected at runtime via environment variables or
  Kubernetes SealedSecrets (see `kubernetes/README.md`).
- `.env` files are gitignored — use `.env.example` as the template.

## Structure

```
config/
├── .env.example          # Template for local development — copy to .env
├── prometheus/           # Prometheus scrape configs and alerting rules
├── grafana/              # Grafana dashboard JSON exports
└── nginx/                # Nginx reverse proxy configs (if used outside K8s)
```

## Feature Flags

Feature flags are defined in `config/feature_flags.yaml` and loaded at startup.
To enable/disable a flag without redeployment, update the value and send
`SIGHUP` to the API process, or use the admin API endpoint `POST /admin/reload-config`.
