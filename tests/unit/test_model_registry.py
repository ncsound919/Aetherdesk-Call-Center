"""Unit tests for src/api/services/model_registry.py."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.services import model_registry
from api.services.model_registry import (
    ModelRegistry,
    ModelRegistryError,
    _auto_version,
    _validate_version,
    audit_log_model_change,
    get_model_audit_log,
)


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    before = dict(model_registry._registry_cache)
    model_registry._registry_cache.clear()
    yield
    model_registry._registry_cache.clear()
    model_registry._registry_cache.update(before)


class TestValidateVersion:
    def test_valid_version_passes_through(self):
        assert _validate_version(" 1.2.3 ") == "1.2.3"

    def test_invalid_version_raises(self):
        with pytest.raises(ModelRegistryError, match="Invalid version format"):
            _validate_version("v1")

    def test_invalid_version_with_extra(self):
        with pytest.raises(ModelRegistryError):
            _validate_version("1.2")


class TestAutoVersion:
    def test_no_versions(self):
        assert _auto_version([]) == "1.0.0"

    def test_auto_increments_patch(self):
        assert _auto_version(["1.0.0", "2.1.3"]) == "2.1.4"

    def test_auto_ignores_garbage(self):
        assert _auto_version(["abc", "def"]) == "1.0.0"

    def test_mixed_versions(self):
        assert _auto_version(["0.9.0", "not-a-version", "3.0.0"]) == "3.0.1"


class TestRegisterModel:
    @pytest.mark.asyncio
    async def test_with_explicit_version(self):
        with patch(
            "api.services.model_registry.create_model_db",
            new_callable=AsyncMock,
            return_value={
                "id": "m1",
                "tenant_id": "t1",
                "name": "n",
                "version": "1.0.0",
                "model_type": "intent",
                "config_json": "{}",
                "metrics_json": "{}",
                "status": "draft",
            },
        ) as mock_create, patch(
            "api.services.model_registry.audit_log_model_change",
            new_callable=AsyncMock,
        ) as mock_audit:
            result = await ModelRegistry.register_model(
                "t1", "n", version="1.0.0", model_type="intent"
            )
        assert result["version"] == "1.0.0"
        mock_create.assert_awaited_once()
        assert mock_create.call_args.kwargs["config_json"] == "{}"
        mock_audit.assert_awaited_once()
        assert mock_audit.call_args.kwargs["action"] == "registered"

    @pytest.mark.asyncio
    async def test_with_explicit_version_validated(self):
        with patch(
            "api.services.model_registry.create_model_db",
            new_callable=AsyncMock,
            return_value={"id": "m1", "version": "2.0.0", "name": "n"},
        ), patch(
            "api.services.model_registry.list_models_db",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await ModelRegistry.register_model(
                "t1", "n", version="  2.0.0  ", model_type="classifier"
            )

    @pytest.mark.asyncio
    async def test_invalid_explicit_version_raises(self):
        with patch(
            "api.services.model_registry.create_model_db", new_callable=AsyncMock
        ):
            with pytest.raises(ModelRegistryError):
                await ModelRegistry.register_model("t1", "n", version="bad")

    @pytest.mark.asyncio
    async def test_auto_version_uses_list(self):
        with patch(
            "api.services.model_registry.list_models_db",
            new_callable=AsyncMock,
            return_value=[
                {"name": "n", "version": "1.0.0"},
                {"name": "other", "version": "5.0.0"},
            ],
        ), patch(
            "api.services.model_registry.create_model_db",
            new_callable=AsyncMock,
            return_value={"id": "m1", "name": "n", "version": "1.0.1"},
        ) as mock_create, patch(
            "api.services.model_registry.audit_log_model_change",
            new_callable=AsyncMock,
        ):
            await ModelRegistry.register_model("t1", "n", model_type="intent")
        assert mock_create.call_args.kwargs["version"] == "1.0.1"

    @pytest.mark.asyncio
    async def test_create_returns_none_falls_back(self):
        with patch(
            "api.services.model_registry.create_model_db",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "api.services.model_registry.audit_log_model_change",
            new_callable=AsyncMock,
        ):
            result = await ModelRegistry.register_model(
                "t1", "n", version="1.0.0", config={"a": 1}
            )
        assert result["status"] == "draft"
        assert result["tenant_id"] == "t1"
        assert result["config_json"] == json.dumps({"a": 1})
        assert result["id"]

    @pytest.mark.asyncio
    async def test_cache_appended_when_present(self):
        model_registry._registry_cache["t1:intent"] = [{"id": "old"}]
        with patch(
            "api.services.model_registry.create_model_db",
            new_callable=AsyncMock,
            return_value={"id": "m1", "name": "n", "version": "1.0.0"},
        ), patch(
            "api.services.model_registry.audit_log_model_change",
            new_callable=AsyncMock,
        ):
            await ModelRegistry.register_model("t1", "n", version="1.0.0")
        assert len(model_registry._registry_cache["t1:intent"]) == 2
        assert model_registry._registry_cache["t1:intent"][-1]["id"] == "m1"

    @pytest.mark.asyncio
    async def test_metrics_serialized(self):
        with patch(
            "api.services.model_registry.create_model_db",
            new_callable=AsyncMock,
            return_value={"id": "m1", "name": "n", "version": "1.0.0"},
        ) as mock_create, patch(
            "api.services.model_registry.audit_log_model_change",
            new_callable=AsyncMock,
        ):
            await ModelRegistry.register_model(
                "t1", "n", version="1.0.0", metrics={"acc": 0.9}
            )
        assert json.loads(mock_create.call_args.kwargs["metrics_json"]) == {
            "acc": 0.9
        }


class TestTransitionModelState:
    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(ModelRegistryError, match="not found"):
                await ModelRegistry.transition_model_state(
                    "t1", "m1", "1.0.0", "training"
                )

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            return_value={"status": "draft"},
        ):
            with pytest.raises(ModelRegistryError, match="Cannot transition"):
                await ModelRegistry.transition_model_state(
                    "t1", "m1", "1.0.0", "production"
                )

    @pytest.mark.asyncio
    async def test_valid_transition(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            side_effect=[
                {"status": "draft"},
                {"status": "training", "id": "m1"},
            ],
        ), patch(
            "api.services.model_registry.promote_model_db",
            new_callable=AsyncMock,
        ) as mock_promote, patch(
            "api.services.model_registry.audit_log_model_change",
            new_callable=AsyncMock,
        ) as mock_audit:
            result = await ModelRegistry.transition_model_state(
                "t1", "m1", "1.0.0", "training", actor="alice"
            )
        assert result["status"] == "training"
        mock_promote.assert_awaited_once_with("t1", "m1", "1.0.0", "training")
        assert mock_audit.call_args.kwargs["previous_state"] == "draft"
        assert mock_audit.call_args.kwargs["actor"] == "alice"


class TestGetModels:
    @pytest.mark.asyncio
    async def test_get_models(self):
        with patch(
            "api.services.model_registry.list_models_db",
            new_callable=AsyncMock,
            return_value=[{"id": "m1"}],
        ) as mock_list:
            result = await ModelRegistry.get_models("t1", model_type="intent")
        assert result == [{"id": "m1"}]
        assert mock_list.call_args.kwargs["model_type"] == "intent"

    @pytest.mark.asyncio
    async def test_get_model_version_found(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            return_value={"id": "m1", "status": "draft"},
        ):
            result = await ModelRegistry.get_model_version("t1", "m1", "1.0.0")
        assert result == {"id": "m1", "status": "draft"}

    @pytest.mark.asyncio
    async def test_get_model_version_not_found(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await ModelRegistry.get_model_version("t1", "m1", "1.0.0") is None


class TestPromoteModel:
    @pytest.mark.asyncio
    async def test_promote_not_found(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert (
                await ModelRegistry.promote_model("t1", "m1", "1.0.0") is None
            )

    @pytest.mark.asyncio
    async def test_promote_db_returns_none(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            return_value={"status": "staging"},
        ), patch(
            "api.services.model_registry.promote_model_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert (
                await ModelRegistry.promote_model("t1", "m1", "1.0.0") is None
            )

    @pytest.mark.asyncio
    async def test_promote_success(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            return_value={"status": "staging"},
        ), patch(
            "api.services.model_registry.promote_model_db",
            new_callable=AsyncMock,
            return_value={"id": "m1", "status": "production", "name": "n"},
        ), patch(
            "api.services.model_registry.audit_log_model_change",
            new_callable=AsyncMock,
        ) as mock_audit:
            result = await ModelRegistry.promote_model(
                "t1", "m1", "1.0.0", "production"
            )
        assert result["status"] == "production"
        assert mock_audit.call_args.kwargs["action"] == "promoted"
        assert mock_audit.call_args.kwargs["new_state"] == "production"


class TestRollbackModel:
    @pytest.mark.asyncio
    async def test_rollback_not_found(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert (
                await ModelRegistry.rollback_model("t1", "m1", "1.0.0") is None
            )

    @pytest.mark.asyncio
    async def test_rollback_db_returns_none(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            return_value={"status": "production"},
        ), patch(
            "api.services.model_registry.rollback_model_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert (
                await ModelRegistry.rollback_model("t1", "m1", "1.0.0") is None
            )

    @pytest.mark.asyncio
    async def test_rollback_success(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            return_value={"status": "production"},
        ), patch(
            "api.services.model_registry.rollback_model_db",
            new_callable=AsyncMock,
            return_value={"id": "m1", "status": "staging"},
        ), patch(
            "api.services.model_registry.audit_log_model_change",
            new_callable=AsyncMock,
        ) as mock_audit:
            result = await ModelRegistry.rollback_model("t1", "m1", "1.0.0")
        assert result["status"] == "staging"
        assert mock_audit.call_args.kwargs["new_state"] == "staging"


class TestActiveModelAndFamily:
    @pytest.mark.asyncio
    async def test_get_active_model_found(self):
        with patch(
            "api.services.db_ai_platform.get_active_model_db",
            new_callable=AsyncMock,
            return_value={"id": "m1", "name": "n"},
        ):
            result = await ModelRegistry.get_active_model("t1", "intent")
        assert result == {"id": "m1", "name": "n"}

    @pytest.mark.asyncio
    async def test_get_active_model_not_found(self):
        with patch(
            "api.services.db_ai_platform.get_active_model_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await ModelRegistry.get_active_model("t1") is None

    @pytest.mark.asyncio
    async def test_get_model_family_filters(self):
        with patch(
            "api.services.model_registry.list_models_db",
            new_callable=AsyncMock,
            return_value=[
                {"model_type": "llm"},
                {"model_type": "classifier"},
            ],
        ):
            result = await ModelRegistry.get_model_family("t1", "llm")
        assert result == [{"model_type": "llm"}]


class TestExternalJobs:
    @pytest.mark.asyncio
    async def test_link_external_job(self):
        with patch(
            "api.services.model_registry.create_external_job_db",
            new_callable=AsyncMock,
            return_value={"id": "j1"},
        ) as mock_create:
            result = await ModelRegistry.link_external_job(
                "t1", "m1", "1.0.0", "ext-1", "modal"
            )
        assert result == {"id": "j1"}
        assert mock_create.call_args.kwargs["external_provider"] == "modal"

    @pytest.mark.asyncio
    async def test_link_external_job_none(self):
        with patch(
            "api.services.model_registry.create_external_job_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert (
                await ModelRegistry.link_external_job("t1", "m1", "1.0.0", "e")
                is None
            )

    @pytest.mark.asyncio
    async def test_list_external_jobs(self):
        with patch(
            "api.services.model_registry.list_external_jobs_db",
            new_callable=AsyncMock,
            return_value=[{"id": "j1"}],
        ):
            assert await ModelRegistry.list_external_jobs("t1", "m1") == [{"id": "j1"}]


class TestEvaluationMetrics:
    @pytest.mark.asyncio
    async def test_ingest_with_transition(self):
        with patch(
            "api.services.model_registry.create_eval_metrics_db",
            new_callable=AsyncMock,
            return_value={"id": "e1"},
        ), patch(
            "api.services.model_registry.ModelRegistry.transition_model_state",
            new_callable=AsyncMock,
        ) as mock_transition:
            result = await ModelRegistry.ingest_evaluation_metrics(
                "t1", "m1", "1.0.0", {"acc": 0.9}
            )
        assert result == {"id": "e1"}
        mock_transition.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ingest_transition_error_is_caught(self):
        with patch(
            "api.services.model_registry.create_eval_metrics_db",
            new_callable=AsyncMock,
            return_value={"id": "e1"},
        ), patch(
            "api.services.model_registry.ModelRegistry.transition_model_state",
            new_callable=AsyncMock,
            side_effect=ModelRegistryError("nope"),
        ):
            result = await ModelRegistry.ingest_evaluation_metrics(
                "t1", "m1", "1.0.0", {}
            )
        assert result == {"id": "e1"}

    @pytest.mark.asyncio
    async def test_ingest_no_record(self):
        with patch(
            "api.services.model_registry.create_eval_metrics_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert (
                await ModelRegistry.ingest_evaluation_metrics("t1", "m1", "1.0.0", {})
                is None
            )

    @pytest.mark.asyncio
    async def test_get_evaluation_metrics(self):
        with patch(
            "api.services.model_registry.get_eval_metrics_db",
            new_callable=AsyncMock,
            return_value=[{"acc": 0.9}],
        ):
            assert await ModelRegistry.get_evaluation_metrics(
                "t1", "m1", "1.0.0"
            ) == [{"acc": 0.9}]


class TestCompareModels:
    @pytest.mark.asyncio
    async def test_one_missing_returns_error(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await ModelRegistry.compare_models("t1", "m1", "1.0.0", "2.0.0")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_compare_numeric_and_string_metrics(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            side_effect=[
                {
                    "status": "approved",
                    "metrics_json": '{"accuracy": 0.8, "note": "hi"}',
                    "created_at": "t1",
                },
                {
                    "status": "production",
                    "metrics_json": '{"accuracy": 0.9, "note": "ho"}',
                    "created_at": "t2",
                },
            ],
        ):
            result = await ModelRegistry.compare_models("t1", "m1", "1.0.0", "2.0.0")
        assert result["diff"]["accuracy"]["a"] == 0.8
        assert result["diff"]["accuracy"]["b"] == 0.9
        assert result["diff"]["accuracy"]["delta"] == 0.1
        assert result["diff"]["accuracy"]["better"] is True
        assert result["diff"]["note"] == {"a": "hi", "b": "ho"}

    @pytest.mark.asyncio
    async def test_compare_dict_metrics_and_non_accuracy(self):
        with patch(
            "api.services.model_registry.get_model_version_db",
            new_callable=AsyncMock,
            side_effect=[
                {"status": "approved", "metrics_json": {"latency": 100.0}},
                {"status": "production", "metrics_json": {"latency": 80.0}},
            ],
        ):
            result = await ModelRegistry.compare_models("t1", "m1", "1.0.0", "2.0.0")
        # latency: lower is better
        assert result["diff"]["latency"]["delta"] == -20.0
        assert result["diff"]["latency"]["better"] is True


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_audit_log_model_change(self):
        with patch(
            "api.services.model_registry.create_model_audit_log_db",
            new_callable=AsyncMock,
        ) as mock_create:
            await audit_log_model_change(
                tenant_id="t1",
                model_id="m1",
                version="1.0.0",
                action="registered",
                previous_state=None,
                new_state="draft",
                actor="system",
            )
        mock_create.assert_awaited_once()
        assert mock_create.call_args.kwargs["action"] == "registered"

    @pytest.mark.asyncio
    async def test_get_model_audit_log(self):
        with patch(
            "api.services.model_registry.get_model_audit_log_db",
            new_callable=AsyncMock,
            return_value=[{"action": "registered"}],
        ):
            assert await get_model_audit_log("t1", "m1") == [{"action": "registered"}]
