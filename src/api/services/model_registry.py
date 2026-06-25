import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from api.services.db_ai_platform import (
    create_eval_metrics_db,
    create_external_job_db,
    create_model_audit_log_db,
    create_model_db,
    get_eval_metrics_db,
    get_model_audit_log_db,
    get_model_version_db,
    list_external_jobs_db,
    list_models_db,
    promote_model_db,
    rollback_model_db,
)

logger = structlog.get_logger()

MODEL_FAMILIES = ["llm", "classifier", "summarizer", "sentiment", "intent", "voice_biometric"]

LIFECYCLE_STATES = ["draft", "training", "trained", "evaluated", "approved", "production", "retired"]

_ALLOWED_TRANSITIONS = {
    "draft": {"training"},
    "training": {"trained"},
    "trained": {"evaluated"},
    "evaluated": {"approved"},
    "approved": {"production"},
    "production": {"retired"},
    "retired": set(),
    "staging": {"production"},
}


class ModelRegistryError(Exception):
    pass


def _validate_version(version: str) -> str:
    version = version.strip()
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        raise ModelRegistryError(f"Invalid version format '{version}'. Must be X.Y.Z (e.g. 1.0.0)")
    return version


def _auto_version(existing_versions: list[str]) -> str:
    if not existing_versions:
        return "1.0.0"
    nums = []
    for v in existing_versions:
        m = re.match(r"(\d+)\.(\d+)\.(\d+)", v)
        if m:
            nums.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    if nums:
        nums.sort()
        major, minor, patch = nums[-1]
        return f"{major}.{minor}.{patch + 1}"
    return "1.0.0"


_registry_cache: dict[str, list[dict]] = {}


class ModelRegistry:
    @staticmethod
    async def register_model(
        tenant_id: str,
        name: str,
        version: str | None = None,
        model_type: str = "intent",
        config: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> dict:
        if config is None:
            config = {}
        if metrics is None:
            metrics = {}

        if version:
            version = _validate_version(version)
        else:
            existing = await list_models_db(tenant_id)
            existing_versions = [m["version"] for m in existing if m.get("name") == name]
            version = _auto_version(existing_versions)

        model = await create_model_db(
            tenant_id=tenant_id,
            name=name,
            version=version,
            model_type=model_type,
            config_json=json.dumps(config),
            metrics_json=json.dumps(metrics),
        )
        if not model:
            model_id = str(uuid.uuid4())
            now = datetime.now(UTC).isoformat()
            model = {
                "id": model_id,
                "tenant_id": tenant_id,
                "name": name,
                "version": version,
                "model_type": model_type,
                "config_json": json.dumps(config),
                "metrics_json": json.dumps(metrics),
                "status": "draft",
                "created_at": now,
            }

        cache_key = f"{tenant_id}:{model_type}"
        if cache_key in _registry_cache:
            _registry_cache[cache_key].append(model)

        await audit_log_model_change(
            tenant_id=tenant_id,
            model_id=model["id"],
            version=version,
            action="registered",
            previous_state=None,
            new_state="draft",
            actor="system",
        )
        logger.info("registered_model", name=name, version=version, model_type=model_type)
        return model

    @staticmethod
    async def transition_model_state(
        tenant_id: str,
        model_id: str,
        version: str,
        new_state: str,
        actor: str = "system",
    ) -> dict | None:
        current = await get_model_version_db(tenant_id, model_id, version)
        if not current:
            raise ModelRegistryError(f"Model {model_id} v{version} not found")

        current_state = current.get("status", "draft")
        if new_state not in _ALLOWED_TRANSITIONS.get(current_state, set()):
            raise ModelRegistryError(
                f"Cannot transition from '{current_state}' to '{new_state}'. "
                f"Allowed: {_ALLOWED_TRANSITIONS.get(current_state, set())}"
            )

        await promote_model_db(tenant_id, model_id, version, new_state)
        await audit_log_model_change(
            tenant_id=tenant_id,
            model_id=model_id,
            version=version,
            action="state_change",
            previous_state=current_state,
            new_state=new_state,
            actor=actor,
        )
        logger.info("transitioned_model_state", model_id=model_id, version=version, from_state=current_state, to_state=new_state)
        return await get_model_version_db(tenant_id, model_id, version)

    @staticmethod
    async def get_models(tenant_id: str, model_type: str | None = None) -> list[dict]:
        return await list_models_db(tenant_id, model_type=model_type)

    @staticmethod
    async def get_model_version(tenant_id: str, model_id: str, version: str) -> dict | None:
        model = await get_model_version_db(tenant_id, model_id, version)
        if model:
            return dict(model)
        return None

    @staticmethod
    async def promote_model(tenant_id: str, model_id: str, version: str, environment: str = "production") -> dict | None:
        current = await get_model_version_db(tenant_id, model_id, version)
        if not current:
            return None
        old_state = current.get("status", "staging")
        model = await promote_model_db(tenant_id, model_id, version, environment)
        if model:
            await audit_log_model_change(
                tenant_id=tenant_id,
                model_id=model_id,
                version=version,
                action="promoted",
                previous_state=old_state,
                new_state=environment,
                actor="system",
            )
            logger.info("promoted_model", model_id=model_id, version=version, environment=environment)
            return dict(model)
        return None

    @staticmethod
    async def rollback_model(tenant_id: str, model_id: str, version: str) -> dict | None:
        current = await get_model_version_db(tenant_id, model_id, version)
        if not current:
            return None
        old_state = current.get("status", "production")
        model = await rollback_model_db(tenant_id, model_id, version)
        if model:
            await audit_log_model_change(
                tenant_id=tenant_id,
                model_id=model_id,
                version=version,
                action="rolled_back",
                previous_state=old_state,
                new_state="staging",
                actor="system",
            )
            logger.info("rolled_back_model", model_id=model_id, version=version)
            return dict(model)
        return None

    @staticmethod
    async def get_active_model(tenant_id: str, model_type: str = "intent") -> dict | None:
        from api.services.db_ai_platform import get_active_model_db
        model = await get_active_model_db(tenant_id, model_type)
        if model:
            return dict(model)
        return None

    @staticmethod
    async def get_model_family(tenant_id: str, family: str) -> list[dict]:
        all_models = await list_models_db(tenant_id)
        return [m for m in all_models if m.get("model_type") == family]

    @staticmethod
    async def link_external_job(
        tenant_id: str,
        model_id: str,
        version: str,
        external_job_id: str,
        external_provider: str = "modal",
    ) -> dict | None:
        record = await create_external_job_db(
            tenant_id=tenant_id,
            model_id=model_id,
            version=version,
            external_job_id=external_job_id,
            external_provider=external_provider,
        )
        if record:
            logger.info("linked_external_job", model_id=model_id, version=version, job_id=external_job_id)
        return record

    @staticmethod
    async def list_external_jobs(tenant_id: str, model_id: str) -> list[dict]:
        return await list_external_jobs_db(tenant_id, model_id)

    @staticmethod
    async def ingest_evaluation_metrics(
        tenant_id: str,
        model_id: str,
        version: str,
        metrics: dict[str, Any],
    ) -> dict | None:
        record = await create_eval_metrics_db(
            tenant_id=tenant_id,
            model_id=model_id,
            version=version,
            metrics_json=json.dumps(metrics),
        )
        if record:
            try:
                await ModelRegistry.transition_model_state(
                    tenant_id=tenant_id,
                    model_id=model_id,
                    version=version,
                    new_state="evaluated",
                    actor="system",
                )
            except ModelRegistryError:
                pass
            logger.info("ingested_eval_metrics", model_id=model_id, version=version)
        return record

    @staticmethod
    async def get_evaluation_metrics(tenant_id: str, model_id: str, version: str) -> list[dict]:
        return await get_eval_metrics_db(tenant_id, model_id, version)

    @staticmethod
    async def compare_models(
        tenant_id: str,
        model_id: str,
        version_a: str,
        version_b: str,
    ) -> dict:
        model_a = await get_model_version_db(tenant_id, model_id, version_a)
        model_b = await get_model_version_db(tenant_id, model_id, version_b)

        if not model_a or not model_b:
            return {"error": "One or both versions not found"}

        metrics_a = json.loads(model_a.get("metrics_json", "{}")) if isinstance(model_a.get("metrics_json"), str) else model_a.get("metrics_json", {})
        metrics_b = json.loads(model_b.get("metrics_json", "{}")) if isinstance(model_b.get("metrics_json"), str) else model_b.get("metrics_json", {})

        comparison = {
            "model_id": model_id,
            "version_a": {
                "version": version_a,
                "status": model_a.get("status"),
                "metrics": metrics_a,
                "created_at": model_a.get("created_at"),
            },
            "version_b": {
                "version": version_b,
                "status": model_b.get("status"),
                "metrics": metrics_b,
                "created_at": model_b.get("created_at"),
            },
            "diff": {},
        }

        all_keys = set(metrics_a.keys()) | set(metrics_b.keys())
        for key in sorted(all_keys):
            val_a = metrics_a.get(key)
            val_b = metrics_b.get(key)
            if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                comparison["diff"][key] = {
                    "a": val_a,
                    "b": val_b,
                    "delta": round(val_b - val_a, 4),
                    "better": val_b > val_a if key in ("accuracy", "precision", "recall", "f1") else val_b < val_a,
                }
            else:
                comparison["diff"][key] = {"a": val_a, "b": val_b}

        return comparison


async def audit_log_model_change(
    tenant_id: str,
    model_id: str,
    version: str,
    action: str,
    previous_state: str | None = None,
    new_state: str | None = None,
    actor: str | None = None,
):
    await create_model_audit_log_db(
        tenant_id=tenant_id,
        model_id=model_id,
        version=version,
        action=action,
        previous_state=previous_state,
        new_state=new_state,
        actor=actor,
    )


async def get_model_audit_log(tenant_id: str, model_id: str) -> list[dict]:
    return await get_model_audit_log_db(tenant_id, model_id)
