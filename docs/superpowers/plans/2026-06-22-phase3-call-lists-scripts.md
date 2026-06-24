# Phase 3: Call Lists & Scripts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement robust call list management (CSV/Excel import, mapping, CRUD, bulk actions) and a flexible script/template system with versioning and a visual editor.

**Architecture:** Expand `leads` table with new columns. Create a new `scripts` table for versioned content. Create `script_templates` table for marketplace. Add `leads` and `scripts` routers. Implement lead scoring and script variable substitution.

**Tech Stack:** FastAPI, Pandas (for CSV/Excel parsing), Pydantic, structlog, React, react-router-dom, Tailwind CSS.

**Note:** For local dev, a simple CSV parser will be used. Full Excel support (using openpyxl) will be added if needed for production.

---

## File Structure

### Backend (New/Modified)

| File | Action | Purpose |
|------|--------|---------|
| `apps/api/services/db_schema.py` | Modify | Add `scripts` table, update `leads` table columns, add `script_templates` table |
| `apps/api/services/db_tenants.py` | Modify | Add CRUD for leads and scripts, lead scoring helpers |
| `apps/api/routers/leads.py` | Create | Upload, map-columns, import, CRUD, bulk actions for leads |
| `apps/api/routers/scripts.py` | Create | List, create, update, delete scripts, template management |
| `apps/api/main.py` | Modify | Register leads and scripts routers |
| `tests/unit/test_leads.py` | Create | Tests for lead management endpoints |
| `tests/unit/test_scripts.py` | Create | Tests for script management endpoints |

### Frontend (New/Modified)

| File | Action | Purpose |
|------|--------|---------|
| `agent-ui/src/lib/api.ts` | Modify | Add lead and script methods |
| `agent-ui/src/pages/LeadsPage.tsx` | Create | Table with filters, bulk actions, import button |
| `agent-ui/src/pages/LeadImportPage.tsx` | Create | Standalone lead import page |
| `agent-ui/src/pages/ScriptsPage.tsx` | Create | Script list and template gallery |
| `agent-ui/src/pages/ScriptEditorPage.tsx` | Create | Block-based script editor |
| `agent-ui/src/App.tsx` | Modify | Add `/leads`, `/scripts`, `/scripts/editor/:id` routes |
| `agent-ui/src/components/onboarding/StepImportLeads.tsx` | Modify | Integrate with new lead import API |
| `agent-ui/src/components/onboarding/StepWriteScript.tsx` | Modify | Integrate with new script API |

---

## Task 1: Add scripts/lead-scoring columns to db_schema.py

**Files:**
- Modify: `apps/api/services/db_schema.py`

- [ ] **Step 1: Add `scripts` table (PostgreSQL)**

Open `apps/api/services/db_schema.py`. Add the `scripts` table definition after `agent_profiles` table (around line 609):

```sql
-- Scripts
CREATE TABLE IF NOT EXISTS scripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    content JSONB NOT NULL DEFAULT '{}',  -- JSON: {blocks: [...], variables: [...], branches: [...]}
    variables JSONB DEFAULT '[]',  -- [{name, type, default, source}]
    is_active BOOLEAN DEFAULT FALSE,
    version INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_scripts_tenant ON scripts(tenant_id);
```

- [ ] **Step 2: Add `script_templates` table (PostgreSQL)**

Add the `script_templates` table definition after `scripts` table:

```sql
-- Script Templates
CREATE TABLE IF NOT EXISTS script_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    industry VARCHAR(100),
    content JSONB NOT NULL DEFAULT '{}',
    variables JSONB DEFAULT '[]',
    is_public BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

- [ ] **Step 3: Update `leads` table columns (PostgreSQL)**

Find the `leads` table definition (around line 643). Modify it to include new columns:

```sql
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    company_name VARCHAR(255),
    contact_name VARCHAR(255),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(20) NOT NULL,
    email VARCHAR(255),
    industry VARCHAR(100),
    notes TEXT,
    priority INT DEFAULT 5,
    status VARCHAR(50) DEFAULT 'new',
    score FLOAT DEFAULT 0.0,
    source VARCHAR(100),  -- csv, api, manual
    imported_at TIMESTAMPTZ,
    last_called_at TIMESTAMPTZ,
    custom_fields JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

- [ ] **Step 4: Add `scripts` table (SQLite)**

In the same file, find `SQLITE_SCHEMA_SQL`. Add the `scripts` table definition after `rentals` table (around line 599):

```sql
CREATE TABLE IF NOT EXISTS scripts (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL, content TEXT DEFAULT '{}',
    variables TEXT DEFAULT '[]', is_active INTEGER DEFAULT 0,
    version INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_scripts_tenant ON scripts(tenant_id);
```

- [ ] **Step 5: Add `script_templates` table (SQLite)**

Add the `script_templates` table definition after `scripts` table:

```sql
CREATE TABLE IF NOT EXISTS script_templates (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
    description TEXT, industry TEXT,
    content TEXT DEFAULT '{}', variables TEXT DEFAULT '[]',
    is_public INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 6: Update `leads` table columns (SQLite)**

Find the `leads` table definition (around line 643). Modify it to include new columns:

```sql
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    company_name TEXT, contact_name TEXT, first_name TEXT, last_name TEXT,
    phone TEXT NOT NULL, email TEXT, industry TEXT, notes TEXT,
    priority INTEGER DEFAULT 5, status TEXT DEFAULT 'new', score REAL DEFAULT 0.0,
    source TEXT, imported_at TIMESTAMP, last_called_at TIMESTAMP,
    custom_fields TEXT DEFAULT '{}', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 7: Verify schema loads without errors**

Run: `python -c "from apps.api.services.db_schema import SCHEMA_SQL, SQLITE_SCHEMA_SQL; print('PostgreSQL OK'); print('SQLite OK')"`
Expected: Both print OK

- [ ] **Step 8: Commit**

```bash
git add apps/api/services/db_schema.py
git commit -m "feat: add scripts/script_templates tables, expand leads table"
```

---

## Task 2: Add lead + script CRUD DB helpers in db_tenants.py

**Files:**
- Modify: `apps/api/services/db_tenants.py`

- [ ] **Step 1: Add `create_lead_db`, `get_lead_db`, `list_leads_db`, `update_lead_db`, `delete_lead_db`**

Append to `apps/api/services/db_tenants.py` at the end of the file (after Task 4 helpers):

```python
# --- Leads ---

async def create_lead_db(tenant_id: str, company_name: str, phone: str, contact_name: str = None, first_name: str = None, last_name: str = None, email: str = None, industry: str = None, notes: str = None, priority: int = 5, status: str = "new", score: float = 0.0, source: str = "manual", imported_at: str = None, custom_fields: dict = None):
    """Create a new lead."""
    lead_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO leads (
                   id, tenant_id, company_name, contact_name, first_name, last_name, phone, email, industry, notes, priority, status, score, source, imported_at, custom_fields, created_at, updated_at
                   ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, NOW(), NOW())""",
                lead_id, tenant_id, company_name, contact_name, first_name, last_name, phone, email, industry, notes, priority, status, score, source, imported_at, json.dumps(custom_fields or {})
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO leads (
               id, tenant_id, company_name, contact_name, first_name, last_name, phone, email, industry, notes, priority, status, score, source, imported_at, custom_fields, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (lead_id, tenant_id, company_name, contact_name, first_name, last_name, phone, email, industry, notes, priority, status, score, source, imported_at, json.dumps(custom_fields or {}), now, now)
        )
        conn.commit()
        conn.close()
    return {"id": lead_id}


async def get_lead_db(lead_id: str, tenant_id: str):
    """Get a single lead by ID."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM leads WHERE id = $1 AND tenant_id = $2", lead_id, tenant_id)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE id = ? AND tenant_id = ?", (lead_id, tenant_id))
        row = cursor.fetchone()
        conn.close()
        return row


async def list_leads_db(tenant_id: str, status: str = None, industry: str = None, limit: int = 100, offset: int = 0):
    """List leads with filters."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = "SELECT * FROM leads WHERE tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if status:
                query += f" AND status = ${idx}"; params.append(status); idx += 1
            if industry:
                query += f" AND industry ILIKE ${idx}"; params.append(f'%{industry}%'); idx += 1
            query += f" ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}"
            params.extend([limit, offset])
            return await conn.fetch(query, *params)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        query = "SELECT * FROM leads WHERE tenant_id = ?"
        params = [tenant_id]
        if status:
            query += " AND status = ?"; params.append(status)
        if industry:
            query += " AND industry LIKE ?"; params.append(f'%{industry}%')
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        conn.close()
        return rows


async def update_lead_db(lead_id: str, tenant_id: str, updates: dict):
    """Update a lead's fields."""
    if not updates: return None
    
    set_clauses = []
    values = []
    idx = 1
    for key, value in updates.items():
        if key == "custom_fields":
            set_clauses.append(f"custom_fields = custom_fields || ${idx}")
            values.append(json.dumps(value))
        else:
            set_clauses.append(f"{key} = ${idx}") # nosec B608
            values.append(value)
        idx += 1
    set_clauses.append(f"updated_at = NOW()")

    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = f"UPDATE leads SET {', '.join(set_clauses)} WHERE id = ${idx} AND tenant_id = ${idx+1}"
            values.extend([lead_id, tenant_id])
            await conn.execute(query, *values)
            return await get_lead_db(lead_id, tenant_id)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        set_clauses_sqlite = []
        values_sqlite = []
        for key, value in updates.items():
            if key == "custom_fields":
                # SQLite json_patch equivalent (simplified for this context)
                # This is a basic merge, more complex logic might be needed for real JSON patching
                existing_cf_json = conn.execute("SELECT custom_fields FROM leads WHERE id = ? AND tenant_id = ?", (lead_id, tenant_id)).fetchone()
                existing_cf = json.loads(existing_cf_json[0]) if existing_cf_json and existing_cf_json[0] else {}
                merged_cf = {**existing_cf, **value}
                set_clauses_sqlite.append(f"custom_fields = ?")
                values_sqlite.append(json.dumps(merged_cf))
            else:
                set_clauses_sqlite.append(f"{key} = ?") # nosec B608
                values_sqlite.append(value)
        set_clauses_sqlite.append(f"updated_at = datetime('now')")

        query = f"UPDATE leads SET {', '.join(set_clauses_sqlite)} WHERE id = ? AND tenant_id = ?"
        values_sqlite.extend([lead_id, tenant_id])
        cursor.execute(query, tuple(values_sqlite))
        conn.commit()
        row = await get_lead_db(lead_id, tenant_id)
        conn.close()
        return row


async def delete_lead_db(lead_id: str, tenant_id: str) -> bool:
    """Delete a lead."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM leads WHERE id = $1 AND tenant_id = $2", lead_id, tenant_id)
            return result != "DELETE 0"
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leads WHERE id = ? AND tenant_id = ?", (lead_id, tenant_id))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0


async def bulk_update_leads_db(tenant_id: str, lead_ids: list[str], updates: dict):
    """Bulk update leads by IDs."""
    if not lead_ids or not updates: return 0
    
    set_clauses = []
    values = []
    idx = 1
    for key, value in updates.items():
        if key == "custom_fields":
            # For simplicity in bulk, overwrite or shallow merge. Deep merge is complex in SQL.
            set_clauses.append(f"custom_fields = custom_fields || ${idx}")
            values.append(json.dumps(value))
        else:
            set_clauses.append(f"{key} = ${idx}") # nosec B608
            values.append(value)
        idx += 1
    set_clauses.append(f"updated_at = NOW()")

    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = f"UPDATE leads SET {', '.join(set_clauses)} WHERE id = ANY(${idx}) AND tenant_id = ${idx+1}"
            values.extend([lead_ids, tenant_id])
            result = await conn.execute(query, *values)
            return int(result.split()[-1]) # Return count of updated rows
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        affected_rows = 0
        for lid in lead_ids:
            set_clauses_sqlite = []
            values_sqlite = []
            for key, value in updates.items():
                if key == "custom_fields":
                    existing_cf_json = conn.execute("SELECT custom_fields FROM leads WHERE id = ? AND tenant_id = ?", (lid, tenant_id)).fetchone()
                    existing_cf = json.loads(existing_cf_json[0]) if existing_cf_json and existing_cf_json[0] else {}
                    merged_cf = {**existing_cf, **value}
                    set_clauses_sqlite.append(f"custom_fields = ?")
                    values_sqlite.append(json.dumps(merged_cf))
                else:
                    set_clauses_sqlite.append(f"{key} = ?") # nosec B608
                    values_sqlite.append(value)
            set_clauses_sqlite.append(f"updated_at = datetime('now')")
            query = f"UPDATE leads SET {', '.join(set_clauses_sqlite)} WHERE id = ? AND tenant_id = ?"
            values_sqlite.extend([lid, tenant_id])
            cursor.execute(query, tuple(values_sqlite))
            affected_rows += cursor.rowcount
        conn.commit()
        conn.close()
        return affected_rows


async def bulk_delete_leads_db(tenant_id: str, lead_ids: list[str]) -> int:
    """Bulk delete leads by IDs."""
    if not lead_ids: return 0
    
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = "DELETE FROM leads WHERE id = ANY($1) AND tenant_id = $2"
            result = await conn.execute(query, lead_ids, tenant_id)
            return int(result.split()[-1])
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        placeholders = ', '.join(['?' for _ in lead_ids])
        query = f"DELETE FROM leads WHERE id IN ({placeholders}) AND tenant_id = ?"
        cursor.execute(query, tuple(lead_ids + [tenant_id]))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected

# --- Scripts ---

async def create_script_db(tenant_id: str, name: str, content: dict, variables: list[dict] = None) -> dict:
    """Create a new script."""
    script_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO scripts (id, tenant_id, name, content, variables, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, NOW(), NOW())""",
                script_id, tenant_id, name, json.dumps(content), json.dumps(variables or [])
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO scripts (id, tenant_id, name, content, variables, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (script_id, tenant_id, name, json.dumps(content), json.dumps(variables or []), now, now)
        )
        conn.commit()
        conn.close()
    return {"id": script_id}


async def get_script_db(script_id: str, tenant_id: str) -> Optional[dict]:
    """Get a script by ID."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM scripts WHERE id = $1 AND tenant_id = $2", script_id, tenant_id)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scripts WHERE id = ? AND tenant_id = ?", (script_id, tenant_id))
        row = cursor.fetchone()
        conn.close()
    
    if row and isinstance(row, dict):
        row["content"] = json.loads(row["content"]) if isinstance(row["content"], str) else row["content"]
        row["variables"] = json.loads(row["variables"]) if isinstance(row["variables"], str) else row["variables"]
    elif row and hasattr(row, 'keys'): # sqlite.Row
        row_dict = {k: row[k] for k in row.keys()}
        row_dict["content"] = json.loads(row_dict["content"]) if isinstance(row_dict["content"], str) else row_dict["content"]
        row_dict["variables"] = json.loads(row_dict["variables"]) if isinstance(row_dict["variables"], str) else row_dict["variables"]
        return row_dict

    return row


async def list_scripts_db(tenant_id: str, is_active: bool = None, limit: int = 100, offset: int = 0) -> list[dict]:
    """List scripts for a tenant."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = "SELECT * FROM scripts WHERE tenant_id = $1"
            params = [tenant_id]
            idx = 2
            if is_active is not None:
                query += f" AND is_active = ${idx}"; params.append(is_active); idx += 1
            query += f" ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}"
            params.extend([limit, offset])
            rows = await conn.fetch(query, *params)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        query = "SELECT * FROM scripts WHERE tenant_id = ?"
        params = [tenant_id]
        if is_active is not None:
            query += " AND is_active = ?"; params.append(1 if is_active else 0)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        conn.close()
    
    parsed_rows = []
    for row in rows:
        if isinstance(row, dict):
            row["content"] = json.loads(row["content"]) if isinstance(row["content"], str) else row["content"]
            row["variables"] = json.loads(row["variables"]) if isinstance(row["variables"], str) else row["variables"]
            parsed_rows.append(row)
        elif hasattr(row, 'keys'): # sqlite.Row
            row_dict = {k: row[k] for k in row.keys()}
            row_dict["content"] = json.loads(row_dict["content"]) if isinstance(row_dict["content"], str) else row_dict["content"]
            row_dict["variables"] = json.loads(row_dict["variables"]) if isinstance(row_dict["variables"], str) else row_dict["variables"]
            parsed_rows.append(row_dict)
    return parsed_rows


async def update_script_db(script_id: str, tenant_id: str, updates: dict) -> Optional[dict]:
    """Update a script's fields."""
    if not updates: return None
    
    set_clauses = []
    values = []
    idx = 1
    if "content" in updates: # Special handling for JSONB
        set_clauses.append(f"content = ${idx}")
        values.append(json.dumps(updates["content"])) # Ensure JSON is dumped
        idx += 1
    if "variables" in updates: # Special handling for JSONB
        set_clauses.append(f"variables = ${idx}")
        values.append(json.dumps(updates["variables"])) # Ensure JSON is dumped
        idx += 1
    if "name" in updates: # String field
        set_clauses.append(f"name = ${idx}")
        values.append(updates["name"])
        idx += 1
    if "is_active" in updates: # Boolean field
        set_clauses.append(f"is_active = ${idx}")
        values.append(updates["is_active"])
        idx += 1
    # Increment version on content change (optional, but good practice)
    if "content" in updates or "variables" in updates:
        set_clauses.append("version = version + 1")
    set_clauses.append("updated_at = NOW()")

    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = f"UPDATE scripts SET {', '.join(set_clauses)} WHERE id = ${idx} AND tenant_id = ${idx+1}"
            values.extend([script_id, tenant_id])
            await conn.execute(query, *values)
            return await get_script_db(script_id, tenant_id)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        # SQLite doesn't have native JSONB update/merge, so we'll fetch, update, then save
        existing_script = await get_script_db(script_id, tenant_id)
        if not existing_script: return None

        update_values = []
        update_clauses = []

        if "content" in updates:
            existing_content = existing_script.get("content", {}) if isinstance(existing_script.get("content"), dict) else json.loads(existing_script.get("content", "{}"))
            merged_content = {**existing_content, **updates["content"]}
            update_clauses.append("content = ?")
            update_values.append(json.dumps(merged_content))
        
        if "variables" in updates:
            update_clauses.append("variables = ?")
            update_values.append(json.dumps(updates["variables"]))

        if "name" in updates:
            update_clauses.append("name = ?")
            update_values.append(updates["name"])

        if "is_active" in updates:
            update_clauses.append("is_active = ?")
            update_values.append(1 if updates["is_active"] else 0)
        
        update_clauses.append("version = version + 1")
        update_clauses.append("updated_at = datetime('now')")

        if update_clauses:
            query = f"UPDATE scripts SET {', '.join(update_clauses)} WHERE id = ? AND tenant_id = ?"
            update_values.extend([script_id, tenant_id])
            cursor.execute(query, tuple(update_values))
            conn.commit()
        
        row = await get_script_db(script_id, tenant_id)
        conn.close()
        return row


async def delete_script_db(script_id: str, tenant_id: str) -> bool:
    """Delete a script."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM scripts WHERE id = $1 AND tenant_id = $2", script_id, tenant_id)
            return result != "DELETE 0"
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM scripts WHERE id = ? AND tenant_id = ?", (script_id, tenant_id))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

# --- Script Templates ---

async def get_script_template_db(template_id: str) -> Optional[dict]:
    """Get a script template by ID."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM script_templates WHERE id = $1", template_id)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM script_templates WHERE id = ?", (template_id,))
        row = cursor.fetchone()
        conn.close()
    
    if row and isinstance(row, dict):
        row["content"] = json.loads(row["content"]) if isinstance(row["content"], str) else row["content"]
        row["variables"] = json.loads(row["variables"]) if isinstance(row["variables"], str) else row["variables"]
    elif row and hasattr(row, 'keys'): # sqlite.Row
        row_dict = {k: row[k] for k in row.keys()}
        row_dict["content"] = json.loads(row_dict["content"]) if isinstance(row_dict["content"], str) else row_dict["content"]
        row_dict["variables"] = json.loads(row_dict["variables"]) if isinstance(row_dict["variables"], str) else row_dict["variables"]
        return row_dict

    return row


async def list_script_templates_db(industry: str = None, limit: int = 100, offset: int = 0) -> list[dict]:
    """List public script templates."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            query = "SELECT * FROM script_templates WHERE is_public = TRUE"
            params = []
            idx = 1
            if industry:
                query += f" AND industry ILIKE ${idx}"; params.append(f'%{industry}%'); idx += 1
            query += f" ORDER BY name ASC LIMIT ${idx} OFFSET ${idx+1}"
            params.extend([limit, offset])
            rows = await conn.fetch(query, *params)
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        query = "SELECT * FROM script_templates WHERE is_public = 1"
        params = []
        if industry:
            query += " AND industry LIKE ?"; params.append(f'%{industry}%')
        query += " ORDER BY name ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        conn.close()

    parsed_rows = []
    for row in rows:
        if isinstance(row, dict):
            row["content"] = json.loads(row["content"]) if isinstance(row["content"], str) else row["content"]
            row["variables"] = json.loads(row["variables"]) if isinstance(row["variables"], str) else row["variables"]
            parsed_rows.append(row)
        elif hasattr(row, 'keys'): # sqlite.Row
            row_dict = {k: row[k] for k in row.keys()}
            row_dict["content"] = json.loads(row_dict["content"]) if isinstance(row_dict["content"], str) else row_dict["content"]
            row_dict["variables"] = json.loads(row_dict["variables"]) if isinstance(row_dict["variables"], str) else row_dict["variables"]
            parsed_rows.append(row_dict)
    return parsed_rows


async def create_script_template_db(name: str, description: str, industry: str, content: dict, variables: list[dict], is_public: bool = True) -> dict:
    """Create a new script template (e.g., from an existing script to publish to marketplace)."""
    template_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO script_templates (id, name, description, industry, content, variables, is_public, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())""",
                template_id, name, description, industry, json.dumps(content), json.dumps(variables or []), is_public
            )
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO script_templates (id, name, description, industry, content, variables, is_public, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (template_id, name, description, industry, json.dumps(content), json.dumps(variables or []), 1 if is_public else 0, now, now)
        )
        conn.commit()
        conn.close()
    return {"id": template_id}


async def delete_script_template_db(template_id: str) -> bool:
    """Delete a script template."""
    if USE_POSTGRES:
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM script_templates WHERE id = $1", template_id)
            return result != "DELETE 0"
    else:
        conn = _get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM script_templates WHERE id = ?", (template_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0
