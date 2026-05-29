# Agent Call Center Build Plan

## Context Brief

You are building an **agent call center** platform ("AetherDesk") using existing scaffolding and trending open-source tools. The goal is to enhance the current IVR/protocol engine with voice capabilities (ASR/TTS), AI agents, and real-time call orchestration.

## Current State

The project already has:

- **FastAPI backend** (`apps/api/main.py`) with Redis-backed session management
- **Protocol VM engine** (`services/engine.py`) — a state machine that runs JSON-defined IVR flows with validation, routing, and actions
- **Queue management** (`services/queue.py`) — Redis-based work distribution for agent handoff
- **Two-question router** (`services/router.py`) — routes incoming requests to protocols based on intent detection
- **Protocol definitions** in `config/protocols/*.json` (e.g., billing_invoice_v1, pharmacy_refill_v1)
- **Route configuration** in `config/routes.json` — maps intent combinations to protocols and queues
- **Starter agent UI** (`agent-ui/`) — React/Vite scaffold
- **Twilio webhook stub** — ready for telephony integration

## Target Architecture

```
[Twilio/Asterisk] ──> [Voice Gateway API (FastAPI)] ──> [Protocol VM + ASR/TTS]
                                                          │
                                          ┌───────────────┴───────────────┐
                                          ▼                               ▼
                                    [Queue Manager]              [AI Agent Layer]
                                    (Redis-backed)                  (Open Source LLMs)
                                          │                               │
                                          ▼                               ▼
                                    [Agent UI] <────────────── [Knowledge Base + RAG]
```

## Key Open-Source Tools to Integrate

Based on trending GitHub repos (April 2025):

| Layer | Tool | Stars | Why |
|-------|------|-------|-----|
| **ASR** | `faster-whisper` (SYSTRAN) | 22k+ | 4x faster than openai/whisper, CTranslate2 optimization |
| **TTS** | `RealtimeTTS` (KoljaB) | 3.8k | Low-latency, multi-engine support (Coqui, Piper, Edge TTS) |
| **LLM Serving** | `Ollama` | 100k+ | "Docker for LLMs" — simplest local deployment, OpenAI-compatible API |
| **RAG** | `LangChain` + `ChromaDB` | 125k/?? | LangChain ecosystem (125k stars), ChromaDB for lightweight vector store |
| **Telephony** | Twilio Media Streams | — | Existing webhook stub ready; real-time WebSocket audio |
| **Orchestration** | RFC pipeline patterns | — | Multi-agent call flow from ECC skills |

### Alternative considerations:
- **TTS alternatives**: `Piper` (fast, low-resource), `Coqui TTS` (high quality), `Soprano` (80M params, 20x realtime on CPU)
- **LLM Serving alternatives**: vLLM (production throughput), but Ollama simpler for dev
- **RAG alternatives**: LlamaIndex (46k stars, better for complex data), LightRAG (27k, graph-based)

## Build Steps

### Step 1: Voice Gateway — Integrate ASR/TTS into FastAPI

- **Goal**: Add endpoints that accept audio (Twilio Media Stream), transcribe with Whisper, synthesize responses with TTS.
- **Tools**: `faster-whisper`, `RealtimeTTS`
- **Tasks**:
  1. Add `faster-whisper` and `RealtimeTTS` to requirements
  2. Create `services/asr.py` — async transcription wrapper using faster-whisper (CTranslate2 optimization, 4x faster)
  3. Create `services/tts.py` — async synthesis wrapper using RealtimeTTS (supports Coqui, Piper, Edge TTS)
  4. Extend `routers/webhooks_twilio.py` to handle Twilio Media Stream (WebSocket `/media-stream`)
  5. Create `routers/voice.py` — endpoint to stream audio back to caller
- **Verification**: `curl` a sample audio file to `/api/v1/voice/transcribe` and get text; call `/api/v1/voice/synthesize` and get audio back.

### Step 2: Connect Voice Gateway to Protocol VM

- **Goal**: Enable the Protocol VM to speak and listen instead of just processing text.
- **Tasks**:
  1. Modify `services/engine.py` to support audio prompts (return TTS audio instead of text prompts)
  2. Add `VMState.audio_prompt` field to hold synthesized audio path
  3. Create `services/call_session.py` — manage voice call lifecycle, buffer audio, feed to ASR after each TTS turn
  4. Update `routers/voice.py` to initialize a `ProtocolVM` per call and drive the turn-taking loop
- **Verification**: Twilio call hits webhook, hears TTS prompt, can speak back and get routed through protocol.

### Step 3: Add LLM-Powered Intent Detection (Replace Two-Question Router)

- **Goal**: Use an open-source LLM to classify caller intent from transcribed speech instead of relying on DTMF or fixed two-question pattern.
- **Tools**: `Ollama` (OpenAI-compatible API, llama3.2/qwen models)
- **Tasks**:
  1. Add `ollama` (Python client library) to requirements
  2. Create `services/intent_classifier.py` — prompt LLM to extract intent + entities from transcript
  3. Update `services/router.py` to use intent classifier instead of two-question lookup
  4. Define a schema for intent output (intent name, entities, confidence)
- **Verification**: Send transcript "I need to refill my prescription" → returns `{intent: "pharmacy_refill", entities: {}}`.

### Step 4: AI Agent Response Generation (Knowledge Base + RAG)

- **Goal**: Instead of simple protocol actions, generate dynamic responses using a knowledge base.
- **Tools**: `LangChain` (125k stars), `ChromaDB`, `sentence-transformers` (embeddings)
- **Tasks**:
  1. Add `langchain`, `langchain-community`, `chromadb`, `sentence-transformers` to requirements
  2. Create sample knowledge base (FAQ docs, policy docs in `data/kb/`)
  3. Create `services/rag.py` — retrieve relevant context from KB given user query using ChromaDB + LangChain
  4. Create `services/agent.py` — LLM generates response given KB context + conversation history (Ollama for LLM)
  5. Integrate into protocol actions — replace static "lookup_invoice" with `rag.answer()` for applicable nodes
- **Verification**: Query "What's my invoice status?" → retrieves invoice from KB, LLM generates natural response.

### Step 5: Multi-Agent Orchestration (Call Flow Control)

- **Goal**: Coordinate multiple specialized agents (billing agent, pharmacy agent, general triage) based on call stage.
- **Tasks**:
  1. Refactor `services/agent.py` into specialized agent classes (BillingAgent, PharmacyAgent, TriageAgent)
  2. Create `services/orchestrator.py` — routes call to appropriate agent based on protocol state
  3. Add `dmux` or RFC pipeline pattern for parallel agent consultations (e.g., while agent handles billing, pre-fetch pharmacy records)
  4. Add conversation summary / context handoff when escalating to human agent
- **Verification**: Call flow: greeting → triage (TriageAgent) → billing (BillingAgent) → handoff to human with summary.

### Step 6: Enhanced Agent UI for Live Calls

- **Goal**: Real-time agent dashboard to take over calls, see transcript, KB suggestions.
- **Tasks**:
  1. Add WebSocket endpoint for real-time transcript streaming (`routers/realtime.py`)
  2. Extend `agent-ui/src/components/Inbox.tsx` with call panel, live transcript, suggested responses
  3. Add "take call" button in UI that claims from queue and streams audio
  4. Add KB search UI component for agent to query while on call
- **Verification**: Agent sees incoming call in UI, clicks "Take", sees live transcript, can speak to caller.

### Step 7: Observability + Production Hardening

- **Goal**: Logging, metrics, error handling, health checks.
- **Tasks**:
  1. Add `structlog` or `opentelemetry` to FastAPI
  2. Add Prometheus metrics for: calls per minute, avg call duration, intent classification confidence, ASR/TTS latency
  3. Add health check endpoint (`/health`) that verifies Redis, ASR model, TTS model, LLM endpoint
  4. Add error recovery in voice gateway (restart ASR on failure, fallback to DTMF)
- **Verification**: `curl /metrics` shows call stats; health check returns 200 only when all dependencies up.

### Step 8: Deployment (Docker Compose)

- **Goal**: One-command startup for local dev and staging.
- **Tasks**:
  1. Create `docker-compose.yml` with services: FastAPI, Redis, Ollama (LLM), faster-whisper (ASR), RealtimeTTS (TTS), Agent UI
  2. Add `Dockerfile` for FastAPI service
  3. Add `Dockerfile` for Agent UI (or use Vite preview mode)
  4. Add `docker-compose.override.yml` for local development (volumes, ports)
- **Reference repos for docker patterns**:
  - Twilio Media Stream + FastAPI: https://github.com/twilio-samples/speech-assistant-openai-realtime-api-python
  - Ollama docker: https://github.com/ollama/ollama
- **Verification**: `docker compose up` brings up all services; Twilio can reach webhook from ngrok tunnel.

## Dependency Graph

```
Step 1 (Voice Gateway) ──┐
                         ├──> Step 2 (Connect to VM) ──> Step 3 (LLM Intent)
                         │                                │
                         │                                └──> Step 4 (RAG + Agent)
                         │                                           │
                         │                                           └──> Step 5 (Orchestration)
                         │
Step 6 (Agent UI) <─────┘                                    Step 7 (Observability)
       │                                                        │
       └──────────────────> Step 8 (Docker Compose) <─────────┘
```

**Parallel opportunities**:
- Step 1 and Step 6 can run in parallel (voice backend vs UI)
- Step 4 and Step 5 can run in parallel after Step 3 is done

## Model Tier Recommendations

| Step | Complexity | Model Recommendation |
|------|------------|----------------------|
| Step 1 | Low-medium | Default (no LLM) |
| Step 2 | Medium | Default |
| Step 3 | High (prompt design) | Strongest (Opus) |
| Step 4 | High (RAG + generation) | Strongest |
| Step 5 | High (orchestration logic) | Strongest |
| Step 6 | Medium | Default |
| Step 7 | Low | Default |
| Step 8 | Low | Default |

## Rollback Strategy per Step

- **Step 1**: If ASR/TTS unstable, fall back to Twilio built-in transcription + text-to-speech; revert voice endpoints to simple text-only mode.
- **Step 2**: If Protocol VM audio integration breaks, keep text-only mode; revert to existing webhook stub.
- **Step 3**: If LLM intent classification unreliable, fall back to two-question router + DTMF.
- **Step 4**: If RAG quality poor, use static protocol actions (existing code) as fallback.
- **Step 5**: If orchestration complex, keep single-agent flow.
- **Step 6**: If WebSocket issues, use polling-based UI updates.
- **Step 7**: If observability overhead too high, reduce to basic logging.
- **Step 8**: If Docker issues, run services manually with scripts.

## Exit Criteria

After all steps:
- [ ] Twilio call triggers webhook, caller hears TTS prompt, can speak, gets routed through protocol
- [ ] Intent classified via LLM (not DTMF)
- [ ] Dynamic answers from knowledge base (not static)
- [ ] Agent can take call from UI, see live transcript
- [ ] Full call flow observable via metrics
- [ ] `docker compose up` runs entire stack locally