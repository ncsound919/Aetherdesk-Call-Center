# AetherDesk Agents

## Architecture

The actual agent orchestration logic lives in the `src/api/services/` directory:

- **`src/api/services/agent.py`** — Agent lifecycle management, session handling, NLU pipeline
- **`src/api/services/orchestrator.py`** — Multi-agent orchestration, call routing, task coordination

This `agents/` directory is reserved for **future** standalone agent orchestration modules, including:

- Specialized agent type packages (e.g., sales, support, triage bots)
- Agent team definitions and composition logic
- Scenario-based agent evaluation harnesses

## Current Contents

- `migration-supervisor.md` — Agent prompt/instructions for a code-migration review supervisor (used during the `apps/` → `src/` restructuring)
