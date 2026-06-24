# Extract Call Management Routes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract call management routes from `apps/api/main.py` into a new router file `apps/api/routers/calls.py`.

**Architecture:** Create a new `APIRouter` for call-related routes in `apps/api/routers/calls.py` and include it in the main FastAPI application in `apps/api/main.py`.

**Tech Stack:** FastAPI, Python, dependency injection.

---

### Task 1: Initialize router directory and file

**Files:**
- Create: `apps/api/routers/__init__.py` (if not exists)
- Create: `apps/api/routers/calls.py`

- [ ] **Step 1: Ensure directory exists and create file**

```bash
# Verify parent directory exists - it should
if not (Test-Path "apps/api/routers") { New-Item -ItemType Directory -Path "apps/api/routers" }
# Create __init__.py if needed, usually best practice in FastAPI
if not (Test-Path "apps/api/routers/__init__.py") { New-Item -ItemType File -Path "apps/api/routers/__init__.py" }
```

- [ ] **Step 2: Create `apps/api/routers/calls.py`**

(I need to see `main.py` imports to correctly import dependencies)

### Task 2: Implement `apps/api/routers/calls.py`

(Requires reading `apps/api/main.py` imports to ensure correct dependencies are imported in the new file)

- [ ] **Step 1: Populate `apps/api/routers/calls.py` with routes and necessary imports**

### Task 3: Update `apps/api/main.py`

- [ ] **Step 1: Import the new router**
- [ ] **Step 2: Include the new router in the app**
- [ ] **Step 3: Remove the extracted routes from `apps/api/main.py`**

### Task 4: Verify and Commit

- [ ] **Step 1: Run tests**

Run: `python -m pytest tests/unit/ -x -q --tb=short 2>&1`

- [ ] **Step 2: Commit changes**

Run: `git add apps/api/routers/calls.py apps/api/main.py && git commit -m "refactor: extract call management routes from main.py"`
