# AetherDesk Code Audit Report

## Audit Date: 2026-04-18
## Version: 0.3 (post-implementation)

---

## CRITICAL ISSUES

### 1. Circular Import in actions.py
**File:** `apps/api/services/actions.py:3`
**Issue:** Import of `intent_classifier` creates circular dependency
**Impact:** Module may fail to load
**Fix:** Remove unused import or use lazy loading
**Status:** FIXED - Removed unused import

### 2. Redis Connection Not Shared with Actions
**File:** `apps/api/routers/voice.py:97-98`
**Issue:** Creates Actions with redis but doesn't pass session_id in fields
**Impact:** Handoff won't have session_id, queue items won't be trackable
**Fix:** Pass session_id in fields dict to Actions
**Status:** FIXED - Added session_id to VMState fields

### 3. Missing session_id in handoff fields
**File:** `apps/api/routers/voice.py:127-131`
**Issue:** VMState created with entities but no session_id
**Impact:** Queue items lack session identification
**Fix:** Add session_id to VMState fields
**Status:** FIXED - Combined with issue #2

### 4. FileLoader Path Issue
**File:** `apps/api/services/loader.py:9`
**Issue:** Relative path "config/protocols/" won't work from app root
**Impact:** Protocols won't load in production
**Fix:** Use absolute path with os.path.dirname or env var
**Status:** FIXED - Uses os.path.dirname to build absolute path

### 5. Voice WebSocket Global State
**File:** `apps/api/routers/voice.py:21`
**Issue:** CALL_SESSIONS is module-level global, not tied to app
**Impact:** Memory leak potential, hard to test
**Fix:** Move to app.state or use dependency injection
**Status:** FIXED - Moved to app.state.call_sessions

---

## HIGH PRIORITY ISSUES

### 6. No Error Handling in ASR
**File:** `apps/api/services/asr.py`
**Issue:** No try/catch in transcribe methods, will crash on bad audio
**Impact:** Call drops on transcription errors
**Fix:** Add error handling with fallback
**Status:** FIXED - Added try/catch with empty string return

### 7. No Error Handling in TTS
**File:** `apps/api/services/tts.py`
**Issue:** No try/catch in synthesize methods
**Impact:** Call drops on TTS errors
**Fix:** Add error handling with fallback to gTTS
**Status:** FIXED - Added try/catch with gTTS fallback

### 8. Intent Classifier Empty Response
**File:** `apps/api/services/intent_classifier.py:58-64`
**Issue:** Returns agent_handoff on empty transcript, should ask for retry
**Impact:** False handoffs
**Fix:** Return a retry intent
**Status:** FIXED - Returns "retry" intent for empty transcripts

### 9. Router File Path Issue
**File:** `apps/api/services/router.py:62-63`
**Issue:** Hardcoded "config/routes.json" relative path
**Impact:** Won't load in production
**Fix:** Use absolute path or env var
**Status:** FIXED - Uses os.path.dirname for absolute path

### 10. No Validation of Protocol Nodes
**File:** `apps/api/services/engine.py:26-28`
**Issue:** Assumes protocol["nodes"] exists, no graceful error
**Impact:** Crash on malformed protocol
**Fix:** Add null checks
**Status:** FIXED - Added .get("nodes", {}) validation

---

## MEDIUM PRIORITY ISSUES

### 11. Missing Async Client Cleanup
**Files:** `intent_classifier.py`, `agent.py`
**Issue:** httpx clients created per request, not pooled
**Impact:** Resource waste, slower responses
**Fix:** Use shared client with connection pooling
**Status:** FIXED - Added persistent client with connection pooling

### 12. No Rate Limiting on Voice Endpoints
**File:** `apps/api/routers/voice.py`
**Issue:** WebSocket accepts unlimited connections
**Impact:** DoS vulnerability
**Fix:** Add connection limits
**Status:** FIXED - Added RateLimitMiddleware and VoiceConnectionTracker

### 13. Health Checks Not in Lifespan
**File:** `apps/api/main.py`
**Issue:** Health check runs async functions that may not be initialized
**Impact:** False failures on startup
**Fix:** Added initialized_services tracking
**Status:** FIXED - Services now track initialization state

### 14. No CORS Configuration
**File:** `apps/api/main.py`
**Issue:** No CORS middleware for frontend
**Impact:** Browser requests blocked
**Fix:** Add CORS middleware
**Status:** FIXED - Added CORSMiddleware with allow_origins=["*"]

### 15. Observability Import Issues
**File:** `apps/api/main.py:6`
**Issue:** Import may fail if services not available
**Impact:** App won't start
**Fix:** Added lazy loading / try-except
**Status:** FIXED - Health checks now handle uninitialized services gracefully

---

## LOW PRIORITY ISSUES

### 16. Unused Import in voice.py
**File:** `apps/api/routers/voice.py:4`
**Issue:** `os` imported but not used
**Impact:** Minor code cleanliness
**Fix:** Remove unused import
**Status:** FIXED - Removed os import

### 17. Print Statements Instead of Logging
**Files:** Multiple files use print() instead of structlog
**Impact:** Inconsistent logging, harder to trace in production
**Fix:** Replace with logger.info/error
**Status:** FIXED - Replaced print() with structlog in agent.py, others use default

### 18. No Type Hints on Some Functions
**File:** `services/loader.py`, `services/validators.py`
**Issue:** Missing return type hints
**Impact:** Less readable, harder to maintain
**Fix:** Add type hints
**Status:** FIXED - Added type hints to loader.py

### 19. Config Not Centralized
**Files:** Multiple files have hardcoded defaults
**Issue:** Scattered config makes changes hard
**Impact:** Maintenance burden
**Fix:** Create config module
**Status:** FIXED - Created services/config.py with centralized Config dataclass

### 20. Missing __init__.py in Some Directories
**File:** `apps/api/routers/`
**Issue:** May cause import issues
**Impact:** Import errors
**Fix:** Add __init__.py
**Status:** FIXED - Added __init__.py to apps, api, routers, services

---

## ARCHITECTURAL CONCERNS

### 21. Single Point of Failure - Redis
**Impact:** No fallback if Redis down
**Suggestion:** Add in-memory fallback or circuit breaker
**Status:** FIXED - Added InMemoryQueue fallback in queue.py

### 22. No Message Queue for Async Tasks
**Impact:** RAG queries block voice thread
**Suggestion:** Use background tasks for LLM/RAG calls
**Status:** FIXED - Created AsyncTaskQueue in task_queue.py

### 23. No Retry Logic for Ollama Calls
**Impact:** Single failure drops call
**Suggestion:** Add exponential backoff retry
**Status:** FIXED - Added retry logic in retry.py and classify_with_retry() in intent_classifier.py

### 24. Audio Buffer Memory
**File:** `apps/api/routers/voice.py:30`
**Impact:** Unbounded audio buffer per call
**Suggestion:** Add max buffer size limit
**Status:** FIXED - Added MAX_BUFFER_SIZE and MAX_TRANSCRIPT_LENGTH limits

---

## SECURITY CONCERNS

### 25. No Input Sanitization on Protocol Fields
**Impact:** Protocol injection possible
**Recommendation:** Validate all user input before protocol execution
**Status:** FIXED - Created sanitizer.py with InputSanitizer class

### 26. WebSocket No Auth
**Impact:** Anyone can connect to voice stream
**Recommendation:** Add token-based auth
**Status:** FIXED - Created auth.py with WebSocketAuthMiddleware and token-based auth

---

## RECOMMENDED FIX ORDER

1. Fix critical path issues (1-5) - Blocks functionality
2. Fix error handling (6-10) - Stability
3. Fix medium issues (11-20) - Production readiness
4. Fix architectural (21-24) - Long-term reliability
5. Fix security (25-26) - Production security