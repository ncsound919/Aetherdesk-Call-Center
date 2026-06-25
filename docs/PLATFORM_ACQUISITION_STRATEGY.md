# AetherDesk — Platform Acquisition Strategy

**Goal:** Transform AetherDesk from a well-architected call center application into a **platform with proprietary AI, developer ecosystem, and embedded distribution** that acquirers cannot replicate in-house.

## Implementation Phases (Hardest → Easiest)

### Phase A: AI Fine-tuning Pipeline & Voice Biometrics
Build proprietary AI IP that creates a defensible moat.

### Phase B: Developer Platform & SDKs
Create platform dynamics with API keys, webhooks, SDKs, and developer portal.

### Phase C: CDP & Data Moat
Aggregate cross-channel customer data and create switching costs.

### Phase D: Vertical SaaS Templates
Pre-built industry solutions for healthcare, finance, real estate, e-commerce.

### Phase E: White-label & Self-serve Onboarding
OEM embedding and frictionless signup flow.

---

## Phase A: AI Fine-tuning Pipeline & Voice Biometrics

### New Files
| File | Purpose |
|------|---------|
| `src/api/services/ai_training.py` | Training data collection, example generation, fine-tuning orchestration |
| `src/api/services/model_registry.py` | Model version tracking, A/B test integration, rollback |
| `src/api/services/voice_biometrics.py` | Speaker identification, emotion detection from audio |
| `src/api/routers/ai_platform.py` | Endpoints for training, models, biometrics |
| `agent-ui/src/pages/AIPlatformDashboard.jsx` | Model management, training status, biometrics |

### Modified Files
| File | Change |
|------|--------|
| `src/api/services/db_schema.py` | Add `ai_models`, `training_jobs`, `voice_profiles`, `emotion_logs` tables |
| `src/api/services/database.py` | Add re-exports |
| `src/api/models/dto.py` | Add DTOs |
| `agent-ui/src/services/api.js` | Add platformApi exports |

---

## Phase B: Developer Platform & SDKs

### New Files
| File | Purpose |
|------|---------|
| `src/api/services/api_keys.py` | API key generation, scoping, rotation, audit |
| `src/api/services/webhook_engine.py` | Event catalog, delivery, retry, dead-letter |
| `src/api/routers/developer.py` | API keys, webhooks, usage analytics |
| `agent-ui/src/pages/DeveloperDashboard.jsx` | Key management, webhook logs, usage stats |
| `sdk/python/aetherdesk/__init__.py` | Python SDK for voice, calls, agents |
| `sdk/python/aetherdesk/client.py` | HTTP client wrapper |
| `sdk/python/aetherdesk/voice.py` | Voice API bindings |

---

## Phase C: CDP & Data Moat

### New Files
| File | Purpose |
|------|---------|
| `src/api/services/cdp.py` | Unified customer profiles, interaction threading, segmentation |
| `src/api/services/customer_analytics.py` | RFM scoring, journey analytics, cohort analysis |
| `src/api/routers/cdp.py` | CDP API endpoints |
| `agent-ui/src/pages/CDPDashboard.jsx` | Customer profiles, segments, analytics |

---

## Phase D: Vertical SaaS Templates

### New Files
| File | Purpose |
|------|---------|
| `src/api/services/vertical_templates.py` | Pre-built vertical configs (healthcare, finance, real estate, ecommerce) |
| `src/api/routers/verticals.py` | Vertical template API |
| `agent-ui/src/pages/VerticalsDashboard.jsx` | Vertical onboarding and template management |

---

## Phase E: White-label & Self-serve

### New Files
| File | Purpose |
|------|---------|
| `src/api/services/white_label.py` | Custom domains, branding, tenant themes |
| `src/api/services/self_serve.py` | Signup flow, automated provisioning, Stripe checkout integration |
| `src/api/routers/platform_ops.py` | White-label, self-serve endpoints |
| `agent-ui/src/pages/WhiteLabelDashboard.jsx` | Branding, domain config |
| `agent-ui/src/pages/SelfServeSetup.jsx` | Onboarding wizard |
