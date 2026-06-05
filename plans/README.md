# `plans/` — Architecture & Planning Documents

This directory contains architectural decision records (ADRs), sprint plans,
and design documents for AetherDesk.

## Naming Convention

```
ADR-NNNN-short-title.md    — Architecture Decision Records
SPRINT-NN-plan.md          — Sprint planning documents
DESIGN-feature-name.md     — Feature-level design specs
```

## Active Documents

| Document | Status | Summary |
|---|---|---|
| `AUDIT_REPORT.md` (root) | Reference | Full agentic readiness audit — 4/10 baseline |
| `AUDIT.md` (root) | Reference | Condensed audit findings |

## Process

Before starting any significant feature or refactor, create a `DESIGN-*.md` here
and get a review. This prevents duplicate implementations and semantic divergence
(a known issue flagged in the audit).
