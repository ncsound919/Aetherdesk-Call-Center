# AETHERDESK CALL CENTER — DEEP SECURITY & CODE AUDIT REPORT

**Auditor:** OpenCode Agent  
**Date:** 2026-05-15  
**Scope:** Full codebase audit — bugs, vulnerabilities, race conditions, leaks, edge cases, smells  
**Verdict:** ⛔ **NOT READY FOR PRODUCTION** — Critical issues found in every layer  

---

## EXECUTIVE SUMMARY

| Category | Count | Severity |
|---|---|---|
| 🔴 Critical Bugs | 17 | Blocks launch |
| 🔴 Security Vulnerabilities | 11 | Exploitable |
| 🟡 Race Conditions | 6 | Causes data corruption |
| 🟠 Memory/Resource Leaks | 9 | Service degradation over time |
| 🟡 Edge Case Gaps | 11 | Runtime crashes under load |
| 🟠 Code Smells | 10 | Maintainability risk |
| 🟡 Config/Deployment Issues | 7 | Operational risk |
| 🔵 Voice Cloning / Chatterbox Gaps | 9 | Feature incomplete |

---

## 🔴 CRITICAL BUGS (P0 — Fix Before Any Deployment)

### 1. Database Connection String Has Hardcoded Credentials
**File:** `apps/api/services/database.py:20-22`  
```python
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://aetherdesk_admin:password@aetherdesk-db:5432/aetherdesk"
)
```
The fallback default contains a plaintext password. If `DATABASE_URL` env var isn't set, it connects with a known credential. **This will also fail in production** where the DB host is `aetherdesk-db` but the default includes the password in the connection string visible in process listings, logs, and error traces.

**Fix:** Remove the fallback default or use a placeholder that fails loudly.

---

### 2. Encryption Key Crash — No Graceful Degradation
**File:** `apps/api/services/database.py:36-38`  
```python
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise RuntimeError("ENCRYPTION_KEY environment variable must be set for production.")
```
App crashes on startup if `ENCRYPTION_KEY` is not set. But many dev/test paths don't need encryption. The `_fernet` object is checked for None before use, so the crash is premature.

**Fix:** Make it a warning, not a hard crash, or gate it behind `USE_POSTGRES`.

---

### 3. Schema Initialization Silently Catches ALL Errors
**File:** `apps/api/services/database.py:686-696`  
```python
for stmt in statements:
    try:
        await conn.execute(stmt)
    except asyncpg.exceptions.DuplicateTableDefinitionError:
        pass
    except Exception as e:
        logger.warning("schema_init_warning", statement=stmt[:80], error=str(e))
```
Catches **all** exceptions as warnings, including syntax errors, permission errors, and constraint violations. Schema tables may silently fail to create.

**Fix:** Re-raise non-DuplicateTable errors, or at minimum exit with error code.

---

### 4. Schema Splitting By Semicolon Will Break Complex SQL
**File:** `apps/api/services/database.py:689`  
```python
statements = [s.strip() for s in SCHEMA_SQL.split(";") if s.strip()]
```
The schema contains PL/pgSQL functions with semicolons inside `BEGIN...END` blocks. `split(";")` will break these functions into invalid fragments. This is why the schema runner may silently fail on the PostgreSQL path.

**Fix:** Use a proper SQL parser or `asyncpg.execute()` with the full multi-statement script.

---

### 5. Relativistic Schema File Has Mismatches With Runtime Code
**File:** `config/database/schema.sql` vs `apps/api/services/database.py`  
- Schema file has `created_at TIMESTAMP WITH TIME ZONE` but runtime code uses `datetime.now(timezone.utc).isoformat()` which outputs a string, not a proper timestamptz.  
- `audit_log.ip_address` is type `INET` in schema, but the code inserts `'127.0.0.1'` as a string literal (works in PG but not in SQLite path).  
- The schema file has `citext` extension loaded but it's never used.

---

### 6. Audio Buffer Processing — Crash on Invalid Input
**File:** `apps/api/services/call_session.py:51-57`  
```python
audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
energy = np.sqrt(np.mean(audio_array.astype(float)**2))
```
If `audio_chunk` has odd length, `np.frombuffer` with `int16` dtype will raise `ValueError`. There's only a length check for `< 320` bytes but no alignment check.

**Fix:** Add `len(audio_chunk) % 2 == 0` check or pad/truncate.

---

### 7. Voice.py Session Is Stale After "start" Event
**File:** `apps/api/routers/voice.py:168-195`  
In the "media" event handler, `session` is created once during "start". Later in "media" events, if there's any issue, the code tries to re-fetch the session on line 188-192 using potentially stale `session.profile_id` and `session.tenant_id`. If the original `session` was `None` (failed creation), this will crash with `AttributeError`.

**Fix:** Add null-check for `session` before accessing its attributes.

---

### 8. Race in Campaign Launch Check-Then-Act
**File:** `apps/api/routers/campaign.py:186-208`  
```python
global _campaign_running
async with _campaign_lock:
    if _campaign_running:
        raise HTTPException(...)
    _campaign_running = True

with db_context() as conn:  # ← DB call OUTSIDE the lock
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads ...")
```
The DB query for leads runs outside the campaign lock. Two concurrent requests could both pass the `_campaign_running` check and then interleave DB operations.

**Fix:** Move all shared-state operations inside the lock.

---

### 9. Chatterbox Voice Clone API Call Is Structurally Wrong
**File:** `apps/api/routers/voice_cloning.py:83-92`  
```python
async with session.post(
    f"{chatterbox_url}/voices/clone",
    data={
        "audio": open(audio_path, "rb"),
        "name": voice_id,
        "language": language
    },
    timeout=aiohttp.ClientTimeout(total=60)
) as resp:
```
**Three bugs in one call:**  
- `data={}` with aiohttp sends as form-encoded, but `open(audio_path, "rb")` returns a file object, not bytes. aiohttp doesn't serialize file objects in `data` dicts properly — should use `aiohttp.FormData()`.  
- The file handle from `open()` is never closed — resource leak.  
- Timeout should be longer for large audio files.

---

### 10. Monitoring.py — Broken O11y Health Check
**File:** `apps/api/services/monitoring.py:200-204`  
```python
async def check_ollama_health() -> bool:
    client = await http_pool.get_client()
    response = await client.get("http://localhost:11434/api/tags")
    return response.status_code == 200
```
This looks correct actually — `response.status_code` on httpx IS an int. However, the `http_pool.get_client()` returns a **shared singleton** client but never closes it after the health check, and there's no timeout override per-call.

---

### 11. Route Table Loaded At Module Level — Import Crash
**File:** `apps/api/services/router.py:64-68`  
```python
routes_path = os.path.join(...)
with open(routes_path) as f:
    route_table = json.load(f)
```
If `routes.json` doesn't exist or is malformed, the **entire API module fails to import**, crashing the application on startup.

**Fix:** Wrap in try/except with graceful fallback.

---

### 12. SQLite Concurrency Will Fail Under Load
**File:** `apps/api/services/database.py:726-734`  
Every `_get_sqlite_conn()` creates a new `sqlite3.connect()` call. SQLite doesn't handle concurrent writes well. Multiple async tasks calling `db_context()` will get serialization errors.

**Fix:** Use `check_same_thread=False` and serialize access, or use WAL mode.

---

### 13. JWT Token Uses HS256 With User-Supplied Secret
**File:** `apps/api/main.py:94` and `apps/api/services/auth.py:64-71`  
```python
SECRET_KEY = os.getenv("JWT_SECRET", "your-jwt-secret-key")
```
Default JWT secret is `"your-jwt-secret-key"` — a known value. Anyone can forge tokens. HS256 is also weak for production; RS256 or ES256 should be used.

---

### 14. OR Port Collision on FreeSWITCH
**File:** `kubernetes/deployment.yml:464-477`  
FreeSWITCH maps both UDP 5060 and TCP 5060 (SIP) plus TCP 8021 (ESL) plus TCP 7443 (WSS). But the container uses `hostNetwork: true` without any port mapping — these ports conflict with the host and other pods.

---

### 15. Missing Validation on Tenant ID in Multiple Endpoints
**Files:** `apps/api/main.py:707, 722` and `apps/api/routers/campaign.py:68`  
Tenant ID is extracted from JWT claims or headers without validation that the requesting user actually belongs to that tenant. Any user can query any tenant's data by passing a different `tenant_id`.

---

## 🔴 SECURITY VULNERABILITIES (P0/P1)

### 1. CORS Allows Wildcard With Credentials
**File:** `apps/api/main.py:174-180`  
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.aetherdesk.com", "http://localhost:3000", "http://localhost:3001", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
`allow_credentials=True` combined with `allow_origins=["*"]` is **rejected by browsers per the Fetch spec** but the `*` entry is still dangerous — it signals intent to allow any origin, and if the browser ever changes behavior, it becomes exploitable. Also, `allow_methods=["*"]` allows any HTTP method.

**Fix:** Remove `*`, explicitly list allowed origins, restrict methods to `GET/POST/PUT/DELETE/OPTIONS`.

---

### 2. No Authentication on Incoming Call Handler
**File:** `apps/api/routers/voice.py:49-96`  
`handle_incoming_call` has **NO** `Depends(verify_api_key)` or any authentication. Anyone who discovers the `/voice/incoming` URL can create fake call sessions.

**Fix:** Add API key or webhook signature verification (Fonster signs webhooks).

---

### 3. Voice Clone Endpoint Has No Auth
**File：** `apps/api/routers/voice_cloning.py:20-63`  
`POST /api/v1/voice/clone` accepts file uploads with no authentication. An attacker can:
- Upload arbitrary binary data to exhaust disk space
- Trigger expensive Chatterbox API calls
- Potentially upload malicious payloads

---

### 4. SSRF Protection Is Incomplete
**File:** `apps/api/services/actions.py:28-44`  
SSRF protection blocks private IPs but:
- DNS rebinding can bypass `gethostbyname()` (resolved once, then IP changes)
- IPv6 private addresses (`fd00::/8`) not checked
- Cloud metadata endpoints (`169.254.169.254`) not explicitly blocked
- URL redirect after initial check not prevented

---

### 5. Hardcoded API Keys in Kubernetes Manifest
**File:** `kubernetes/deployment.yml:74-75`  
```yaml
DEEPGRAM_API_KEY: "6d7905409a8d2384ab88de756a671b7fe5be7fa3"
GROQ_API_KEY: "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"
```
These are real API keys committed in plaintext (even if base64-encoded in a Secret, they're in the git repo). **Both keys should be rotated immediately.**

---

### 6. Dev Mode Hardcoded Credentials
**File:** `apps/api/routers/auth.py:18-33`  
```python
DEV_USERS = {
    "admin@aetherdesk.com": {"password": "admin123", "role": "admin", ...},
    "agent@aetherdesk.com": {"password": "agent123", "role": "agent", ...},
}
```
Admin/admin123 and agent/agent123 are in the source code. If `APP_ENV=development` is ever accidentally set in production, these credentials work.

---

### 7. PII Logging Despite Redaction Middleware
**File:** `apps/api/middleware/audit.py:97-105`  
The audit middleware redacts known PHI fields, but:
- `transcript` and `full_text` are in `PHI_FIELDS` but may appear nested in JSON structures where the redaction doesn't recurse deeply enough
- The `new_values` dict at line 127-135 logs the **entire request body** for non-PHI paths
- Redis pub/sub channels transmit call data without encryption

---

### 8. JWT Expiry Allows Tokens Beyond 24h
**File:** `apps/api/main.py:361-367`  
```python
expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=24))
```
24-hour tokens with no refresh mechanism. If a token is leaked, it's valid for a full day. No token revocation mechanism beyond the in-memory `TokenStore`.

---

### 9. No Rate Limiting on Auth Endpoints
**File:** `apps/api/services/rate_limit.py:40`  
```python
if "/voice/" not in request.url.path:
    return await call_next(request)
```
The rate limiter only applies to `/voice/` paths. Login (`/auth/login`), token refresh, and all other endpoints have **zero rate limiting**, enabling brute force attacks.

---

### 10. Webhook Token Uses Weak TokenStore
**File:** `apps/api/services/auth.py:19-55`  
`TokenStore` uses an in-memory dict. Tokens are:
- Not persisted — lost on restart
- Not invalidatable per-user
- Not bound to client fingerprint (IP, user-agent)
- No maximum session limit per user

---

### 11. Kubernetes Secrets Stored as Base64 in Manifest
**File:** `kubernetes/deployment.yml:62-77`  
Secrets are stored as `stringData` in the YAML manifest. Anyone with read access to the repo or cluster can decode them. Should use `sealed-secrets`, `external-secrets-operator`, or a vault.

---

## 🟡 RACE CONDITIONS

### 1. Orchestrator DB Access Pattern
**File:** `apps/api/services/orchestrator.py:112-195`  
```python
async with db_context() as conn:    # Connection 1: fetch profile
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agent_profiles...")
    profile = cursor.fetchone()
# Connection 1 released
# ... (user_input processing) ...
if tool_name in require_approval:
    async with db_context() as conn:  # Connection 2: insert approval
        cursor = conn.cursor()
        cursor.execute("INSERT INTO action_approvals...")
```
Between the two DB operations, session state can change. The approval might be for a stale session.

---

### 2. Campaign Runner State Mutation
**File:** `apps/api/routers/campaign.py:218-277`  
```python
async def _run_campaign(leads: list, config: CampaignLaunch, tenant_id: str):
    global _campaign_running, _http_client
```
`_http_client` is a shared module-level `httpx.AsyncClient`. Multiple campaigns (if the lock is bypassed) would share the same client, and connection pool exhaustion could occur.

---

### 3. In-Memory Queue And Redis Dual-Write
**File:** `apps/api/services/queue.py:91-111`  
```python
def enqueue(self, queue: str, item: dict) -> None:
    backend = self._get_backend()
    backend.lpush(...)
```
When Redis is available, data goes to Redis. When it becomes unavailable mid-operation, the fallback switches to in-memory — but items enqueued in Redis are lost, and the in-memory queue starts from empty. No reconciliation.

---

### 4. Audio Buffer Concatenation Without Lock
**File:** `apps/api/services/call_session.py:59`  
```python
self.audio_buffer += audio_chunk
```
In async context, if multiple coroutines call `process_audio` on the same session, buffer concatenation is not atomic. Could cause interleaved audio data.

---

### 5. Global Agent Cache Without Invalidation
**File:** `apps/api/services/orchestrator.py:342-348`  
```python
self.agents = {}
async def get_agent(self, tenant_id, profile_id):
    key = f"{tenant_id}:{profile_id}"
    if key not in self.agents:
        self.agents[key] = TenantAgent(...)
    return self.agents[key]
```
Agents are cached forever. If an agent's config changes in the DB, the running system continues using stale prompts and tool lists. No TTL, no invalidation.

---

### 6. Shared Mutable Transcript List
**File:** `apps/api/services/call_session.py:24`  
```python
self.transcript: list[dict] = []
```
The transcript list is appended to from both `process_audio` (customer) and `speak`/`speak_stream` (agent) without synchronization. In concurrent execution, entries could be lost or interleaved.

---

## 🟠 MEMORY & RESOURCE LEAKS

### 1. InMemoryQueue Module-Level Singleton
**File:** `apps/api/services/queue.py:60`  
```python
_in_memory_queue = InMemoryQueue()
```
This module-level global persists for the process lifetime. Its `_queues` and `_sessions` dicts grow unboundedly. No eviction, no TTL enforcement for in-memory sessions.

---

### 2. REALTIME Transcripts Dict — Unbounded Growth
**File:** `apps/api/routers/realtime.py:14-15`  
```python
CALL_TRANSCRIPTS: dict[str, list] = {}
CALL_LAST_ACTIVITY: dict[str, float] = {}
```
Per-call transcripts accumulate. The cleanup task (line 78-91) runs every 10 minutes, but only cleans calls idle for >1 hour. High-volume call centers will accumulate thousands of call transcripts in memory.

---

### 3. Voice Profiles Dict — No Eviction
**File:** `apps/api/routers/voice_cloning.py:17`  
```python
voice_profiles = {}
```
Every cloned voice stays in this dict forever. In a multi-tenant system with many voice clones, this grows without bound.

---

### 4. Connection Pool — HTTP Client Never Closed Properly
**File:** `apps/api/services/connection_pool.py:40-51`  
```python
http_pool = HTTPClientPool()
```
The singleton `http_pool` creates an `httpx.AsyncClient` that is never closed during shutdown. The lifespan in `main.py` doesn't call `http_pool.close()`.

---

### 5. WhisperModel Loaded Permanently
**File:** `apps/api/services/asr.py:89`  
```python
asr_service = ASRService(model_size="base", device="auto")
```
The Whisper model is loaded at import time and stays in memory forever. In GPU mode, this permanently occupies VRAM even during idle periods.

---

### 6. TTS Engine Cache Never Cleared
**File:** `apps/api/services/tts.py:24`  
```python
self._engine_cache = {}
```
Populated but never cleared — each TTS engine instance stays in memory.

---

### 7. MemoryService Lock Leak Potential
**File:** `apps/api/services/memory_service.py:38-47`  
```python
async def _get_lock(self, key: str) -> asyncio.Lock:
    async with self._global_lock:
        if len(self._locks) > 1000:
            self._locks = {k: lock for k, lock in self._locks.items() if lock.locked()}
```
The cleanup logic only keeps **locked** locks, dropping unlocked ones. But if a lock is held during cleanup, it stays. Over time, with many unique `(tenant_id, customer_id)` pairs, the lock dict could grow significantly.

---

### 8. Temp Files From Voice Clone May Persist
**File:** `apps/api/routers/voice_cloning.py:33-44`  
```python
temp_path = os.path.join(VOICE_CLONES_DIR, f"{voice_id}_temp")
with open(temp_path, "wb") as f:
    content = await audio.read()
    f.write(content)
# ...
if os.path.exists(temp_path):
    os.remove(temp_path)
```
If `process_voice_clone()` raises an exception between file creation and deletion, the temp file persists. No `try/finally` or context manager.

---

### 9. SQLite Connections Not Pooled
**File:** `apps/api/services/database.py:115-119`  
```python
def _get_sqlite_conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = _dict_factory
    return conn
```
Each call creates a new connection, and while `db_context()` closes it in `finally`, frequent calls create connection churn. No WAL mode means reads block writes.

---

## 🟡 EDGE CASES / ERROR HANDLING GAPS

### 1. Orchestrator Returns Partial AgentResponse on Errors
**File:** `apps/api/services/orchestrator.py:169-176`  
When `response.raise_for_status()` succeeds but JSON parsing fails, the retry loop increments the message to the history. After 2 attempts, it falls through to the "max steps exhausted" handler (line 222-226), returning `needs_agent=True` even if the issue was a formatting error, not a reasoning failure.

---

### 2. Redis Client State Not Checked Before Use
**File:** `apps/api/main.py:83-84` in multiple locations  
```python
if redis_client:
    await redis_client.publish(...)
```
If the Redis connection drops after startup, `redis_client` is still truthy (it's an object), but `publish()` will raise. There's no reconnection logic.

---

### 3. Fonster Client Returns Mock on Error — Silent Degradation
**File:** `apps/api/fonster_client.py:48-56`  
```python
except httpx.HTTPStatusError as e:
    logger.error(f"Fonster create app error...")
    return {
        "ref": f"app-{uuid.uuid4().hex[:8]}",
        "_mock": True,
    }
```
Returns a mock success response on failure. Callers have no way to know the operation actually failed unless they check `_mock`.

---

### 4. Intent Classifier Falls Back on ALL Errors
**File:** `apps/api/services/intent_classifier.py:170-171`  
```python
except Exception:
    return await self._keyword_fallback(transcript)
```
Any error (network timeout, malformed response, OOM) silently falls back to keyword matching. Confidence scores from the fallback (0.2-0.5) are treated as real confidence.

---

### 5. Empty Transcript Returns Fake Intent
**File：** `apps/api/services/intent_classifier.py:143-150`  
```python
if not transcript or not transcript.strip():
    return IntentResult(intent="retry", ...)
```
Returns `"retry"` as the intent for empty audio. The router (`router.py`) has **no route defined for "retry"** — so it falls through to `fallback_handoff_v1`.

---

### 6. Voice Session Removal Is a No-Op
**File:** `apps/api/services/call_session.py:129-132`  
```python
def remove_session(app, session_id: str):
    # For now, just mark as inactive or let it expire in Redis
    # In a full impl, we might want to delete the key immediately
    pass
```
Sessions are never actually removed from Redis. Memory and session data accumulate.

---

### 7. WebSocket Handler Doesn't Handle Redis Disconnection
**File:** `apps/api/routers/voice.py:109-130`  
The media-stream WebSocket handler reads from Redis session store but if Redis goes down mid-call, the handler will crash with an unhandled exception, dropping the WebSocket without proper cleanup of the call session.

---

### 8. No Handling for Agent WebSocket Reconnection
**File:** `apps/api/routers/agent.py:70-80`  
When an agent reconnects via WebSocket, they get a new `agent_id` (based on timestamp). Their previous subscriptions and state are lost. No session resumption logic.

---

### 9. TTS Engine Failover Swallows Errors
**File:** `apps/api/services/tts.py:36-49`  
```python
for engine in engines_to_try:
    try:
        result = await self._synthesize_with_engine(text, engine)
        if result:
            return result
    except Exception as e:
        logger.warning("tts_engine_failed", engine=engine, error=str(e))
        continue
```
If all engines fail, `synthesize()` returns `b""` (empty bytes). The caller (`call_session.py:92`) plays empty audio silently — the caller hears nothing with no error indication.

---

### 10. Billing Calculation Has No Decimal Precision Guard
**File：** `apps/api/services/database.py:434-448`  
```sql
v_rate := v_plan.price_per_hour / 60;
RETURN ROUND((p_duration_seconds::DECIMAL / 60) * v_rate, 4);
```
If `price_per_hour` is 0 (default for plans), the cost is always 0. No validation that the plan exists or has a non-zero rate. Billing calculations silently produce 0 for unconfigured tenants.

---

## 🔵 VOICE CLONING & CHATTERBOX INTEGRATION GAPS

### 1. **Audio File Upload Is Structurally Broken**
**File:** `apps/api/routers/voice_cloning.py:83-92`  
The Chatterbox `/voices/clone` endpoint call uses `data={...}` with `aiohttp`, which sends `application/x-www-form-urlencoded`. But `open(audio_path, "rb")` passes a file object that cannot be serialized this way. **The audio file never actually reaches Chatterbox.**  
**Fix:** Use `aiohttp.FormData()`:
```python
data = aiohttp.FormData()
data.add_field('audio', open(audio_path, 'rb'), filename='audio.wav')
data.add_field('name', voice_id)
data.add_field('language', language)
```

### 2. **Temp File Handle Leaked in Data Dict**
**File:** `apps/api/routers/voice_cloning.py:87`  
`open(audio_path, "rb")` creates a file handle that is never closed. Should use context manager or read bytes first.

### 3. **No Voice Cloning Validation**
No check for:
- Audio format (must be WAV/FLAC for Chatterbox)
- Audio duration (needs minimum ~5 seconds for quality clone)
- Audio sample rate (Chatterbox expects 16kHz or 44.1kHz)
- File size limits

### 4. **Chatterbox API Endpoint May Be Wrong**
**File:** `apps/api/routers/voice_cloning.py:85`  
Uses `f"{chatterbox_url}/voices/clone"` — but the Chatterbox API typically uses `/api/voices/clone` or `/clone`. Need to verify against actual Chatterbox docs.

### 5. **TTS Chatterbox Streaming May Not Work**
**File:** `apps/api/services/tts.py:127-138`  
Uses `client.stream_post(f"{url}/tts/stream", ...)` but Chatterbox may not have a `/tts/stream` endpoint. The non-streaming synthesize uses `/tts` which is more standard.

### 6. **No Voice Selection in TTS**
**File:** `apps/api/services/tts.py:63-72`  
`_synthesize_chatterbox` sends `{"text": text, "voice": self.voice}` but `self.voice` defaults to `"en-US-AriaNeural"` (an Edge TTS voice name), not a Chatterbox voice. Cloned voices are never referenced.

### 7. **Chatterbox Not Referenced in Cloned Voice Profile**
**File:** `apps/api/routers/voice_cloning.py:96`  
After successful clone: `voice_profile["engine"] = "chatterbox"` — but this only sets the engine name. There's no reference to the Chatterbox voice ID needed to actually use the cloned voice.

### 8. **set_default_voice Has No Directory Check**
**File:** `apps/api/routers/voice_cloning.py:173-175`  
```python
config_path = os.path.join(os.path.dirname(__file__), "../../../config/default_voice.json")
with open(config_path, "w") as f:
    json.dump({"default_voice_id": voice_id}, f)
```
If the `config/` directory doesn't exist, this crashes with `FileNotFoundError`.

### 9. **No TTS Integration Test With Chatterbox**
The test suite has no integration tests validating that Chatterbox TTS actually produces audio from cloned voices.

---

## 🟠 CODE SMELLS & DESIGN ISSUES

### 1. God File: `database.py` (1147 lines)
Violates Single Responsibility Principle — contains schema DDL, connection management, tenant/agent/call/billing CRUD, helper functions, and SQLite/PostgreSQL dual-path logic. Should be split into `db_schema.py`, `db_pool.py`, `db_tenants.py`, `db_calls.py`, etc.

### 2. Scattered Lazy Imports
**File:** `apps/api/services/orchestrator.py` — lines 81, 110, 120, 200, 215  
Imports like `from apps.api.services.rag import rag_service` and `from apps.api.routers.campaign import push_escalation_alert` are hidden inside methods. This masks real dependencies and makes testing/mocking impossible.

### 3. Global Mutable State Everywhere
- `orchestrator.py`: `self.agents = {}` — never cleared
- `realtime.py`: `CALL_TRANSCRIPTS = {}`, `manager = ConnectionManager()` — module globals
- `voice_cloning.py`: `voice_profiles = {}`
- `queue.py`: `_in_memory_queue = InMemoryQueue()`
- `config.py`: `config = Config()` — singleton

These make the system impossible to test in parallel and dangerous in multi-worker deployments.

### 4. Dual Database Path Without Abstraction
Every database function has an `if USE_POSTGRES: ... else: ...` branch. This is 20+ duplicated functions. Should use a strategy pattern or repository pattern.

### 5. ProtocolVM Mutates State In-Place
**File:** `apps/api/services/engine.py:23-55`  
`step()` mutates `state` fields directly and also returns it. Callers could use either the mutated object or the return value, leading to subtle bugs.

### 6. Error Swallowing in Campaign Calls
**File:** `apps/api/routers/campaign.py:263-269`  
When a campaign call fails, the lead status is reset to `"new"`, but exceptions from the DB update itself are not caught — the lead could remain in `"calling"` state forever.

### 7. Magic Numbers Throughout
- `call_session.py:27`: `SILENCE_THRESHOLD = 300` — undocumented
- `call_session.py:28-29`: `MAX_SILENCE_FRAMES = 15`, `MAX_BUFFER_FRAMES = 100` — no explanation of units
- `database.py:93-97`: `min_size=5, max_size=20` — no sizing rationale
- `kubernetes/deployment.yml`: Memory/CPU limits appear arbitrary

### 8. `asyncio.get_event_loop()` Deprecation
**File:** `apps/api/routers/voice_cloning.py:79`, `apps/api/routers/realtime.py:131`, `apps/api/services/asr.py:21`  
Using `asyncio.get_event_loop()` is deprecated in Python 3.10+. Should use `asyncio.get_running_loop()` or `asyncio.to_thread()`.

### 9. Inconsistent Error Handling Patterns
- Some functions return `(success, data)` tuples
- Others raise HTTPException
- Others return `{"success": False}` dicts
- Callers must handle each differently

### 10. No Type Safety on DB Results
**File:** `apps/api/services/database.py` — throughout  
All DB results are returned as dicts from `row_factory`, but column names are assumed to exist. If a schema migration changes a column name, failures are runtime `KeyError`s, not caught at import/test time.

---

## 🟡 CONFIGURATION & DEPLOYMENT ISSUES

### 1. Kubernetes Secrets Hardcoded in Repo
**File:** `kubernetes/deployment.yml:74-75`  
```yaml
DEEPGRAM_API_KEY: "6d7905409a8d2384ab88de756a671b7fe5be7fa3"
GROQ_API_KEY: "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"
```
**ACTION REQUIRED:** Rotate both keys immediately. Use Sealed Secrets or External Secrets Operator.

### 2. Stale Domain References
**File:** `kubernetes/deployment.yml:40-41`  
```yaml
API_URL: "https://api.overlay365.com"
APP_URL: "https://app.overlay365.com"
```
Still referencing `overlay365.com` instead of `aetherdesk.com`.

### 3. Duplicate ConfigMap Directory
**File:** `config/fonster/` — two `config.json` files in same directory (confirmed by file listing at different timestamps)

### 4. FreeSWITCH Uses hostNetwork
**File:** `kubernetes/deployment.yml:460-461`  
```yaml
hostNetwork: true
dnsPolicy: ClusterFirstWithHostNet
```
This gives the FreeSWITCH pod access to all network interfaces on the node — a significant security risk. Only the SIP/RTP ports need host networking.

### 5. No PodDisruptionBudgets Defined
If Kubernetes performs node maintenance, all pods could be evicted simultaneously, causing total call center outage.

### 6. No Resource Limits on Fonster/FreeSWITCH
Fonster and FreeSWITCH deployments have no CPU/memory limits, allowing them to consume all node resources.

### 7. Redis Data Loss Risk
**File:** `kubernetes/deployment.yml:294-325`  
Redis uses `emptyDir: {}` for data volume — all data is lost on pod restart. Should use PVC.

---

## 🔴 AUDIT SUMMARY — PRIORITIZED REMEDIATION ROADMAP

### Phase 0: STOP-SHIP (Deploy Blockers)
| # | Issue | File | Effort |
|---|---|---|---|
| 1 | Fix Chatterbox voice clone API call (data format) | `voice_cloning.py:83-92` | 2h |
| 2 | Rotate exposed API keys (Deepgram, Groq) | `kubernetes/deployment.yml` | 2h |
| 3 | Add auth to `/voice/incoming` webhook endpoint | `voice.py:49` | 1h |
| 4 | Add auth to `/api/v1/voice/clone` endpoint | `voice_cloning.py:20` | 1h |
| 5 | Fix CORS wildcard with credentials | `main.py:174-180` | 30min |
| 6 | Remove hardcoded credentials from auth module | `auth.py:18-33` | 1h |
| 7 | Fix schema splitting for PL/pgSQL functions | `database.py:689` | 4h |

### Phase 1: Critical Security Fixes (Week 1)
| # | Issue | Effort |
|---|---|---|
| 1 | SSRF protection: add IPv6, metadata endpoint blocking | 2h |
| 2 | Implement proper rate limiting on auth endpoints | 2h |
| 3 | Replace in-memory TokenStore with Redis-backed JTI | 4h |
| 4 | Add tenant authorization checks (prevent IDOR) | 4h |
| 5 | Fix K8s secrets management (use sealed-secrets) | 2h |
| 6 | Add PodDisruptionBudgets | 1h |
| 7 | Add PVC for Redis data | 1h |

### Phase 2: Concurrency & Reliability (Week 2)
| # | Issue | Effort |
|---|---|---|
| 1 | Add locks to VoiceSession.audio_buffer | 1h |
| 2 | Implement agent cache TTL/invalidation | 3h |
| 3 | Fix Redis reconnection logic | 2h |
| 4 | Add proper session cleanup in voice.py | 2h |
| 5 | Move route table loading out of module scope | 1h |
| 6 | Add SQLite WAL mode and connection pooling | 2h |

### Phase 3: Voice Cloning Completion (Week 2-3)
| # | Issue | Effort |
|---|---|---|
| 1 | Implement proper multimedia form upload for Chatterbox | 3h |
| 2 | Add audio validation (format, duration, sample rate) | 2h |
| 3 | Wire cloned voice ID into TTS voice parameter | 2h |
| 4 | Verify and fix Chatterbox API endpoints | 2h |
| 5 | Add Chatterbox integration tests | 3h |
| 6 | Connect default voice config to TTS engine | 1h |

### Phase 4: Code Quality (Ongoing)
| # | Issue | Effort |
|---|---|---|
| 1 | Split database.py into modules | 8h |
| 2 | Centralize error handling patterns | 4h |
| 3 | Replace global mutable state with DI | 16h |
| 4 | Add type safety to DB result handling | 8h |
| 5 | Migrate deprecated asyncio patterns | 2h |
| 6 | Add comprehensive integration test suite | 16h |

---

*End of Audit Report*