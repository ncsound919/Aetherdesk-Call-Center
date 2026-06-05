# `scripts/` — Operational Scripts

This directory contains one-off operational, migration, and setup scripts.
These are **not** application code — they are run manually by engineers.

## ⚠️ Rules

- Every script must have a docstring or header comment explaining:
  - What it does
  - When to run it
  - What environment it targets (dev / staging / prod)
  - Any destructive side effects
- Scripts that modify production data require a `--confirm` flag.
- Do **not** commit debug scripts, one-time fixups, or test runners here —
  those belong in CI or the test suite.

## Available Scripts

| Script | Purpose | Safe for prod? |
|---|---|---|
| `scripts/seed_demo_data.py` | Seeds a tenant with demo call logs and agents | ❌ dev/staging only |
| `scripts/rotate_api_keys.py` | Rotates Deepgram/Groq keys and updates K8s secrets | ✅ with --confirm |
| `scripts/migrate_file_memory.py` | Migrates file-based long-term memory to Redis | ✅ with --confirm |
