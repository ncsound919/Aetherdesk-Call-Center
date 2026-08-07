"""Tests for src/api/services/db_ai_platform.py — SQLite-backed CRUD for the
AI platform (models, training jobs, datasets, turns/labels, voice profiles,
external jobs, audit logs, eval metrics)."""

import asyncio
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from api.services.database import init_sqlite_schema  # noqa: E402
from api.services.db_pool import _get_sqlite_conn  # noqa: E402

import api.services.db_ai_platform as m  # noqa: E402

TENANT = "tenant-test"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _schema_and_cleanup():
    init_sqlite_schema()
    conn = _get_sqlite_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO tenants (id, name, slug) VALUES (?, 'Test', 'test')",
            (TENANT,),
        )
        conn.commit()
    finally:
        conn.close()
    yield
    conn = _get_sqlite_conn()
    try:
        for table in [
            "ai_models",
            "training_jobs",
            "voice_profiles",
            "emotion_logs",
            "datasets",
            "turns",
            "labels",
            "external_jobs",
            "model_audit_log",
            "eval_metrics",
        ]:
            try:
                conn.execute(f"DELETE FROM {table} WHERE tenant_id = ?", (TENANT,))
            except Exception:
                pass
        conn.execute("DELETE FROM tenants WHERE id = ?", (TENANT,))
        conn.commit()
    finally:
        conn.close()


def test_create_and_list_models():
    model = run(m.create_model_db(TENANT, "intent-model", "1.0", "intent"))
    assert model and model.get("id")
    models = run(m.list_models_db(TENANT))
    assert any(x["id"] == model["id"] for x in models)
    filtered = run(m.list_models_db(TENANT, model_type="intent"))
    assert any(x["id"] == model["id"] for x in filtered)


def test_get_and_version_model():
    model = run(m.create_model_db(TENANT, "svc-model", "1.0", "sentiment"))
    got = run(m.get_model_db(TENANT, model["id"]))
    assert got["id"] == model["id"]
    assert run(m.get_model_db(TENANT, "missing")) is None
    version = run(m.get_model_version_db(TENANT, model["id"], "1.0"))
    assert version is not None


def test_promote_and_rollback_model():
    model = run(m.create_model_db(TENANT, "prod-model", "1.0", "intent"))
    promoted = run(m.promote_model_db(TENANT, model["id"], "1.0", "production"))
    assert promoted is not None
    active = run(m.get_active_model_db(TENANT, "intent"))
    assert active is not None
    rolled = run(m.rollback_model_db(TENANT, model["id"], "1.0"))
    assert rolled is not None
    # Missing model -> None
    assert run(m.promote_model_db(TENANT, "nope", "1.0")) is None
    assert run(m.rollback_model_db(TENANT, "nope", "1.0")) is None


def test_get_active_model_missing():
    assert run(m.get_active_model_db(TENANT, "intent")) is None


def test_training_jobs_crud():
    job = run(m.create_training_job_db(TENANT, "tune-1", "gpt", "{}"))
    assert job and job.get("id")
    got = run(m.get_training_job_db(job["id"]))
    assert got and got["id"] == job["id"]
    assert run(m.get_training_job_db("missing")) is None
    jobs = run(m.list_training_jobs_db(TENANT))
    assert any(j["id"] == job["id"] for j in jobs)
    updated = run(
        m.update_training_job_db(
            job["id"],
            status="completed",
            progress=0.5,
            example_count=10,
            result_json="{}",
            error_message="err",
        )
    )
    assert updated is not None


def test_voice_profiles_and_emotion():
    profile = run(
        m.create_voice_profile_db(TENANT, "Alice", '{"mfcc": [0.1]}')
    )
    assert profile and profile.get("id")
    profiles = run(m.list_voice_profiles_db(TENANT))
    assert any(p["id"] == profile["id"] for p in profiles)

    log = run(m.create_emotion_log_db(TENANT, "call-1", profile["id"], "happy", 0.9))
    assert log is not None
    trends = run(m.get_emotion_trends_db(TENANT, "call-1"))
    assert len(trends) >= 1


def test_datasets_crud():
    ds = run(m.create_dataset_db(TENANT, "ds-1", recipe_type="qa"))
    assert ds and ds.get("id")
    got = run(m.get_dataset_db(ds["id"]))
    assert got and got["id"] == ds["id"]
    assert run(m.get_dataset_db("missing")) is None
    listed = run(m.list_datasets_db(TENANT))
    assert any(d["id"] == ds["id"] for d in listed)
    listed_qa = run(m.list_datasets_db(TENANT, recipe_type="qa"))
    assert any(d["id"] == ds["id"] for d in listed_qa)
    updated = run(
        m.update_dataset_db(
            ds["id"],
            total_examples=5,
            total_turns=2,
            quality_score=0.8,
            stats_json="{}",
            status="ready",
        )
    )
    assert updated is not None


def test_turns_and_labels():
    ds = run(m.create_dataset_db(TENANT, "ds-turns", recipe_type="qa"))
    turn = run(m.create_turn_db(TENANT, dataset_id=ds["id"], text="Hello", speaker="user"))
    assert turn and turn.get("id")
    turns = run(m.list_turns_db(ds["id"]))
    assert any(t["id"] == turn["id"] for t in turns)
    label = run(
        m.create_label_db(TENANT, turn["id"], label_type="intent", label_value="billing", confidence=0.9, notes="")
    )
    assert label is not None
    labels = run(m.list_labels_db(turn["id"]))
    assert any(l["id"] == label["id"] for l in labels)


def test_external_jobs_and_audit_and_metrics():
    model = run(m.create_model_db(TENANT, "ej-model", "1.0", "intent"))
    ej = run(
        m.create_external_job_db(
            TENANT, model["id"], "1.0", "ext-1", "openai", "running"
        )
    )
    assert ej is not None
    jobs = run(m.list_external_jobs_db(TENANT, model["id"]))
    assert any(j["id"] == ej["id"] for j in jobs)

    audit = run(m.create_model_audit_log_db(TENANT, model["id"], "1.0", "registered", actor="admin"))
    assert audit is not None
    logs = run(m.get_model_audit_log_db(TENANT, model["id"]))
    assert any(l["id"] == audit["id"] for l in logs)

    metrics = run(m.create_eval_metrics_db(TENANT, model["id"], "1.0", '{"acc": 0.9}'))
    assert metrics is not None
    got = run(m.get_eval_metrics_db(TENANT, model["id"], "1.0"))
    assert got is not None


class _FakeRow(dict):
    pass


class _FakePool:
    async def fetch(self, query, *params):
        return [_FakeRow({"id": "1", "tenant_id": TENANT, "name": "x"})]

    async def fetchrow(self, query, *params):
        return _FakeRow({"id": "1", "tenant_id": TENANT, "name": "x"})

    async def execute(self, query, *params):
        return None


def test_postgres_branches(monkeypatch):
    """Exercise every function's USE_POSTGRES branch with a fake pool."""
    from unittest.mock import AsyncMock

    monkeypatch.setattr(m, "USE_POSTGRES", True)
    monkeypatch.setattr(m, "get_pg_pool", AsyncMock(return_value=_FakePool()))

    assert run(m.create_model_db(TENANT, "m", "1.0", "intent")) is not None
    assert run(m.list_models_db(TENANT)) == [{"id": "1", "tenant_id": TENANT, "name": "x"}]
    assert run(m.list_models_db(TENANT, model_type="intent")) is not None
    assert run(m.get_model_db(TENANT, "1")) is not None
    assert run(m.get_model_version_db(TENANT, "1", "1.0")) is not None
    assert run(m.promote_model_db(TENANT, "1", "1.0", "production")) is not None
    assert run(m.rollback_model_db(TENANT, "1", "1.0")) is not None
    assert run(m.get_active_model_db(TENANT, "intent")) is not None
    assert run(m.create_training_job_db(TENANT, "j", "gpt", "{}")) is not None
    assert run(m.get_training_job_db("1")) is not None
    assert run(m.list_training_jobs_db(TENANT)) == [
        {"id": "1", "tenant_id": TENANT, "name": "x"}
    ]
    assert run(m.update_training_job_db("1", status="done")) is not None
    assert run(
        m.update_training_job_db(
            "1",
            status="completed",
            progress=0.5,
            example_count=10,
            result_json="{}",
            error_message="err",
        )
    ) is not None
    assert run(m.create_voice_profile_db(TENANT, "A", "{}")) is not None
    assert run(m.list_voice_profiles_db(TENANT)) == [
        {"id": "1", "tenant_id": TENANT, "name": "x"}
    ]
    assert run(m.create_emotion_log_db(TENANT, "c1", "vp1", "happy", 0.9)) is not None
    assert run(m.get_emotion_trends_db(TENANT, "c1")) is not None
    assert run(m.create_dataset_db(TENANT, "ds", recipe_type="qa")) is not None
    assert run(m.list_datasets_db(TENANT)) == [
        {"id": "1", "tenant_id": TENANT, "name": "x"}
    ]
    assert run(m.list_datasets_db(TENANT, recipe_type="qa", limit=10)) is not None
    assert run(m.get_dataset_db("1")) is not None
    assert run(
        m.update_dataset_db(
            "1",
            total_examples=5,
            total_turns=2,
            quality_score=0.8,
            stats_json="{}",
            status="ready",
        )
    ) is not None
    assert run(m.create_turn_db(TENANT, dataset_id="ds", text="hi")) is not None
    assert run(m.list_turns_db("ds")) is not None
    assert run(m.create_label_db(TENANT, "turn-1", label_value="billing")) is not None
    assert run(m.list_labels_db("turn-1")) is not None
    assert run(m.create_external_job_db(TENANT, "m1", "1.0", "ext-1")) is not None
    assert run(m.list_external_jobs_db(TENANT, "m1")) is not None
    assert run(m.create_model_audit_log_db(TENANT, "m1", "1.0", "registered")) is not None
    assert run(m.get_model_audit_log_db(TENANT, "m1")) is not None
    assert run(m.create_eval_metrics_db(TENANT, "m1", "1.0")) is not None
    assert run(m.get_eval_metrics_db(TENANT, "m1", "1.0")) is not None


def test_postgres_no_pool_fallback(monkeypatch):
    """When USE_POSTGRES is on but the pool is unavailable, each function
    returns its empty/default fallback."""
    from unittest.mock import AsyncMock

    monkeypatch.setattr(m, "USE_POSTGRES", True)
    monkeypatch.setattr(m, "get_pg_pool", AsyncMock(return_value=None))

    assert run(m.create_model_db(TENANT, "m", "1.0")) is None
    assert run(m.list_models_db(TENANT)) == []
    assert run(m.get_model_db(TENANT, "1")) is None
    assert run(m.get_model_version_db(TENANT, "1", "1.0")) is None
    assert run(m.promote_model_db(TENANT, "1", "1.0")) is None
    assert run(m.rollback_model_db(TENANT, "1", "1.0")) is None
    assert run(m.get_active_model_db(TENANT, "intent")) is None
    assert run(m.create_training_job_db(TENANT, "j", "gpt")) is None
    assert run(m.get_training_job_db("1")) is None
    assert run(m.list_training_jobs_db(TENANT)) == []
    assert run(m.update_training_job_db("1", status="done")) is None
    assert run(m.create_voice_profile_db(TENANT, "A", "{}")) is None
    assert run(m.list_voice_profiles_db(TENANT)) == []
    assert run(m.create_emotion_log_db(TENANT, "c1", "vp1", "happy", 0.9)) is None
    assert run(m.get_emotion_trends_db(TENANT, "c1")) == []
    assert run(m.create_dataset_db(TENANT, "ds", recipe_type="qa")) is None
    assert run(m.list_datasets_db(TENANT)) == []
    assert run(m.get_dataset_db("1")) is None
    assert run(m.update_dataset_db("1", status="ready")) is None
    assert run(m.create_turn_db(TENANT, dataset_id="ds", text="hi")) is None
    assert run(m.list_turns_db("ds")) == []
    assert run(m.create_label_db(TENANT, "turn-1", label_value="billing")) is None
    assert run(m.list_labels_db("turn-1")) == []
    assert run(m.create_external_job_db(TENANT, "m1", "1.0", "ext-1")) is None
    assert run(m.list_external_jobs_db(TENANT, "m1")) == []
    assert run(m.create_model_audit_log_db(TENANT, "m1", "1.0", "registered")) is None
    assert run(m.get_model_audit_log_db(TENANT, "m1")) == []
    assert run(m.create_eval_metrics_db(TENANT, "m1", "1.0")) is None
    assert run(m.get_eval_metrics_db(TENANT, "m1", "1.0")) == []

