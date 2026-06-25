# Implementation Plan — Phases 5–8: Close Remaining Gaps

**Goal:** Move from 26/40 → 38/40 (65% → 95%) by closing Voice, AI, CX, and Integrations gaps.
**Strategy:** Execute 4 parallel phases, then consolidate in Phase 9.

---

## Phase 5: Voice & Communication Quality (2→4)

### New Files (3)
| File | Purpose |
|------|---------|
| `src/api/services/audio_quality.py` | MOS calculation, jitter/packet loss estimation, quality scoring |
| `src/api/routers/voice_quality.py` | Endpoints for quality metrics, call quality trends |
| `agent-ui/src/pages/VoiceQualityDashboard.jsx` | Real-time quality visualization (MOS, jitter, latency charts) |

### Modified Files (3)
| File | Change |
|------|--------|
| `src/api/services/db_schema.py` | Add `voice_quality_metrics` table (call_id, mos, jitter_ms, packet_loss_pct, latency_ms, codec, created_at) |
| `src/api/services/database.py` | Re-export audio quality DB functions |
| `src/api/models/dto.py` | Add `VoiceQualityMetricCreate`, `VoiceQualityMetricResponse` |

---

## Phase 6: AI & Automation Readiness (3→4)

### New Files (3)
| File | Purpose |
|------|---------|
| `src/api/services/ai_evaluation.py` | Intent accuracy tracking, A/B test framework, confidence thresholds |
| `src/api/routers/ai_ops.py` | Endpoints for AI experiments, accuracy metrics, escalation rules |
| `agent-ui/src/pages/AIOpsDashboard.jsx` | AI metrics dashboard (accuracy, A/B tests, confidence distribution) |

### Modified Files (3)
| File | Change |
|------|--------|
| `src/api/services/db_schema.py` | Add `ai_experiments`, `ai_evaluation_results` tables |
| `src/api/services/database.py` | Re-export AI evaluation DB functions |
| `src/api/models/dto.py` | Add `AIExperimentCreate`, `AIEvaluationResultResponse` |

---

## Phase 7: Customer Experience & UX (2→4)

### New Files (3)
| File | Purpose |
|------|---------|
| `src/api/services/csat.py` | CSAT survey engine, sentiment aggregation, customer 360 queries |
| `src/api/routers/cx.py` | Endpoints for CSAT, sentiment, customer 360 view |
| `agent-ui/src/pages/CXDashboard.jsx` | CX metrics (CSAT scores, sentiment trends, customer history) |

### Modified Files (3)
| File | Change |
|------|--------|
| `src/api/services/db_schema.py` | Add `csat_surveys`, `customer_interactions` tables |
| `src/api/services/database.py` | Re-export CX DB functions |
| `src/api/models/dto.py` | Add `CSATSurveyCreate`, `CustomerInteractionCreate` |

---

## Phase 8: Integrations & Data Infrastructure (3→4)

### New Files (4)
| File | Purpose |
|------|---------|
| `src/api/services/crm_connector.py` | Abstract CRM connector with Salesforce/HubSpot stubs |
| `src/api/services/ticketing.py` | Ticketing integration (Zendesk/ServiceNow stubs) |
| `src/api/routers/integrations.py` | Endpoints for CRM, ticketing, integration health |
| `agent-ui/src/pages/IntegrationsDashboard.jsx` | Integration management (CRM, ticketing, webhooks) |

### Modified Files (3)
| File | Change |
|------|--------|
| `src/api/services/db_schema.py` | Add `integration_configs`, `ticket_sync_log` tables |
| `src/api/services/database.py` | Re-export integration DB functions |
| `src/api/models/dto.py` | Add `IntegrationConfigCreate`, `TicketCreate` |

---

## Phase 9: Consolidation

| File | Change |
|------|--------|
| `src/api/main.py` | Register 4 new routers: voice_quality, ai_ops, cx, integrations |
| `agent-ui/src/App.jsx` | Add 4 new routes: /voice-quality, /ai-ops, /cx, /integrations |
| `agent-ui/src/components/Sidebar.jsx` | Add 4 nav items: Voice Quality, AI Ops, CX, Integrations |
