# `agent_scripts/` — Agent Prompt & Script Templates

This directory contains the prompt templates, conversation scripts, and persona
definitions used by the LangGraph AI agents at runtime.

## Contents

| File/Dir | Purpose |
|---|---|
| `personas/` | System prompt definitions per agent persona (e.g. billing, support, sales) |
| `protocols/` | State machine protocol definitions — maps intents to agent actions |
| `templates/` | Jinja2 / f-string templates for dynamic prompt construction |

## How Scripts Are Loaded

Scripts are loaded at agent startup via `apps/api/services/agent_loader.py`.
Changes to scripts take effect on the next agent session — no server restart required
for prompt changes (hot-reload is supported for `.yaml` and `.txt` templates).

## Adding a New Agent Persona

1. Create a new YAML file in `personas/` following the schema in `personas/_schema.yaml`.
2. Register the persona in `apps/api/services/intent_classifier.py`.
3. Add protocol transitions in `protocols/` if the new persona has unique routing rules.
4. Write unit tests in `tests/unit/test_agent_personas.py`.
