"""Unit tests for src/api/services/security_enhancements.py.

Covers PenetrationTestingService, WAFService, DataClassificationService, and
RBACTestService. External db_* and authorization dependencies are mocked.
"""

from unittest.mock import AsyncMock, patch

import pytest

import api.services.security_enhancements as module
from api.services.security_enhancements import (
    DataClassificationService,
    PenetrationTestingService,
    RBACTestService,
    WAFService,
)


class TestPenetrationTestingService:
    @pytest.mark.asyncio
    async def test_run_scan_success(self):
        with patch.object(
            module,
            "create_pen_test_scan_db",
            new_callable=AsyncMock,
            return_value={"id": "scan-1"},
        ) as create, patch.object(
            module,
            "update_pen_test_scan_db",
            new_callable=AsyncMock,
            return_value={"id": "scan-1"},
        ) as upd, patch.object(
            module,
            "get_pen_test_scan_db",
            new_callable=AsyncMock,
            return_value={"id": "scan-1", "status": "completed"},
        ) as get:
            result = await PenetrationTestingService().run_scan(
                "https://example.com", "t1"
            )
        assert result["status"] == "completed"
        create.assert_awaited_once_with("t1", "https://example.com")
        upd.assert_awaited_once()
        scan_id, status, findings, completed_at = upd.await_args.args
        assert scan_id == "scan-1"
        assert status == "completed"
        assert completed_at is not None
        assert len(findings) == 5
        types = {f["type"] for f in findings}
        assert types == {
            "xss",
            "missing_headers",
            "cors",
            "info_disclosure",
            "ssl",
        }
        get.assert_awaited_once_with("scan-1")

    @pytest.mark.asyncio
    async def test_run_scan_no_scan_created(self):
        with patch.object(
            module,
            "create_pen_test_scan_db",
            new_callable=AsyncMock,
            return_value=None,
        ) as create, patch.object(
            module, "update_pen_test_scan_db", new_callable=AsyncMock
        ) as upd:
            result = await PenetrationTestingService().run_scan(
                "https://example.com", "t1"
            )
        assert result is None
        upd.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_scans(self):
        with patch.object(
            module,
            "list_pen_test_scans_db",
            new_callable=AsyncMock,
            return_value=[{"id": "scan-1"}],
        ) as db:
            result = await PenetrationTestingService().list_scans("t1")
        assert result == [{"id": "scan-1"}]
        db.assert_awaited_once_with("t1")

    @pytest.mark.asyncio
    async def test_get_scan_report(self):
        with patch.object(
            module,
            "get_pen_test_scan_db",
            new_callable=AsyncMock,
            return_value={"id": "scan-1"},
        ) as db:
            result = await PenetrationTestingService().get_scan_report("scan-1")
        assert result == {"id": "scan-1"}
        db.assert_awaited_once_with("scan-1")


class TestWAFService:
    def test_get_waf_rules_returns_copy(self):
        service = WAFService()
        rules = service.get_waf_rules()
        assert len(rules) == 8
        rules.clear()
        assert len(service.get_waf_rules()) == 8

    def test_update_rule_enable(self):
        service = WAFService()
        rule = service.update_waf_rule("waf-006", "enable")
        assert rule["enabled"] is True

    def test_update_rule_disable(self):
        service = WAFService()
        rule = service.update_waf_rule("waf-002", "disable")
        assert rule["enabled"] is False

    def test_update_rule_action_change(self):
        service = WAFService()
        rule = service.update_waf_rule("waf-008", "block")
        assert rule["action"] == "block"

    def test_update_rule_action_log_and_captcha(self):
        service = WAFService()
        assert service.update_waf_rule("waf-001", "log")["action"] == "log"
        assert service.update_waf_rule("waf-001", "captcha")["action"] == "captcha"

    def test_update_rule_not_found(self):
        service = WAFService()
        assert service.update_waf_rule("waf-999", "block") is None

    @pytest.mark.asyncio
    async def test_get_waf_events(self):
        with patch.object(
            module,
            "list_waf_events_db",
            new_callable=AsyncMock,
            return_value=[{"id": "ev-1"}],
        ) as db:
            result = await WAFService().get_waf_events(limit=50, tenant_id="t1")
        assert result == [{"id": "ev-1"}]
        db.assert_awaited_once_with("t1", 50)

    @pytest.mark.asyncio
    async def test_get_waf_events_defaults(self):
        with patch.object(
            module,
            "list_waf_events_db",
            new_callable=AsyncMock,
            return_value=[],
        ) as db:
            await WAFService().get_waf_events()
        db.assert_awaited_once_with("system", 100)


class TestDataClassificationService:
    @pytest.mark.asyncio
    async def test_classify_invalid_sensitivity(self):
        with pytest.raises(ValueError, match="Invalid sensitivity"):
            await DataClassificationService().classify_field(
                "users", "email", "topsecret", "t1"
            )

    @pytest.mark.asyncio
    async def test_classify_valid(self):
        with patch.object(
            module,
            "set_data_classification_db",
            new_callable=AsyncMock,
            return_value={"id": "c1"},
        ) as db:
            result = await DataClassificationService().classify_field(
                "users",
                "email",
                "confidential",
                "t1",
                schema_name="sales",
                description="PII",
            )
        assert result == {"id": "c1"}
        db.assert_awaited_once_with(
            "t1", "sales", "users", "email", "confidential", "PII"
        )

    @pytest.mark.asyncio
    async def test_get_classification_schema(self):
        with patch.object(
            module,
            "get_data_classification_db",
            new_callable=AsyncMock,
            return_value=[{"table_name": "users"}],
        ) as db:
            result = await DataClassificationService().get_classification_schema("t1")
        assert result == [{"table_name": "users"}]
        db.assert_awaited_once_with("t1")

    @pytest.mark.asyncio
    async def test_validate_access_no_classification_default_allow(self):
        with patch.object(
            module,
            "get_data_classification_db",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await DataClassificationService().validate_access(
                "agent", "users", "email", "t1"
            )
        assert result == {"allowed": True, "reason": "No classification found — default allow"}

    @pytest.mark.asyncio
    async def test_validate_access_no_match_for_column_default_allow(self):
        classifications = [
            {"table_name": "users", "column_name": "other", "sensitivity": "restricted"}
        ]
        with patch.object(
            module,
            "get_data_classification_db",
            new_callable=AsyncMock,
            return_value=classifications,
        ):
            result = await DataClassificationService().validate_access(
                "agent", "users", "email", "t1"
            )
        assert result["allowed"] is True

    @pytest.mark.parametrize(
        "role,sensitivity,expected",
        [
            ("admin", "restricted", True),
            ("admin", "confidential", True),
            ("manager", "restricted", False),
            ("manager", "confidential", True),
            ("agent", "confidential", False),
            ("agent", "internal", True),
            ("viewer", "internal", False),
            ("viewer", "public", True),
            ("auditor", "restricted", True),
            ("unknown_role", "public", False),
        ],
    )
    @pytest.mark.asyncio
    async def test_validate_access_role_matrix(self, role, sensitivity, expected):
        classifications = [
            {"table_name": "users", "column_name": "email", "sensitivity": sensitivity}
        ]
        with patch.object(
            module,
            "get_data_classification_db",
            new_callable=AsyncMock,
            return_value=classifications,
        ):
            result = await DataClassificationService().validate_access(
                role, "users", "email", "t1"
            )
        assert result["allowed"] is expected
        assert result["sensitivity"] == sensitivity
        if expected:
            assert result["reason"] == "Access granted"
        else:
            assert f"Role '{role}' cannot access" in result["reason"]


class TestRBACTestService:
    @pytest.mark.asyncio
    async def test_test_role_permissions_passed(self):
        with patch.object(module, "check_permission", return_value=True):
            result = await RBACTestService().test_role_permissions(
                "admin", "calls", "read"
            )
        assert result["passed"] is True
        assert result["expected"] is True
        assert result["actual"] is True
        assert result["role"] == "admin"

    @pytest.mark.asyncio
    async def test_test_role_permissions_failed(self):
        # viewer should NOT write calls; make actual disagree with expected
        with patch.object(module, "check_permission", return_value=True):
            result = await RBACTestService().test_role_permissions(
                "viewer", "calls", "write"
            )
        assert result["expected"] is False
        assert result["actual"] is True
        assert result["passed"] is False

    @pytest.mark.asyncio
    async def test_audit_results_accumulate(self):
        service = RBACTestService()
        with patch.object(module, "check_permission", return_value=True):
            await service.test_role_permissions("admin", "calls", "read")
            await service.test_role_permissions("agent", "billing", "write")
        assert len(service._audit_results) == 2

    @pytest.mark.asyncio
    async def test_run_full_audit(self):
        service = RBACTestService()
        with patch.object(module, "check_permission", return_value=True), patch.object(
            module,
            "create_rbac_audit_result_db",
            new_callable=AsyncMock,
        ) as db:
            results = await service.run_full_audit(tenant_id="t1")
        assert len(results) == 5 * 7 * 3  # roles x resources x actions
        assert db.await_count == 105
        kwargs = db.await_args.kwargs
        assert kwargs["tenant_id"] == "t1"

    @pytest.mark.asyncio
    async def test_get_audit_results_uses_memory(self):
        service = RBACTestService()
        with patch.object(module, "check_permission", return_value=True):
            await service.test_role_permissions("admin", "calls", "read")
        with patch.object(
            module, "list_rbac_audit_results_db", new_callable=AsyncMock
        ) as db:
            results = await service.get_audit_results("t1")
        assert len(results) == 1
        db.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_audit_results_falls_back_to_db(self):
        service = RBACTestService()
        with patch.object(
            module,
            "list_rbac_audit_results_db",
            new_callable=AsyncMock,
            return_value=[{"role": "admin"}, {"role": "viewer"}],
        ) as db:
            results = await service.get_audit_results("t1")
        assert results == [{"role": "admin"}, {"role": "viewer"}]
        db.assert_awaited_once_with("t1")

    @pytest.mark.parametrize(
        "role,resource,action,expected",
        [
            ("admin", "agents", "read", True),
            ("admin", "tenants", "delete", True),
            ("manager", "tenants", "read", False),
            ("manager", "billing", "write", True),
            ("agent", "calls", "read", True),
            ("agent", "agents", "read", False),
            ("agent", "calls", "delete", False),
            ("viewer", "calls", "write", False),
            ("viewer", "scripts", "read", True),
            ("auditor", "tenants", "read", True),
            ("auditor", "tenants", "delete", False),
            ("ghost", "calls", "read", False),
        ],
    )
    def test_get_expected_permission_matrix(self, role, resource, action, expected):
        service = RBACTestService()
        assert service._get_expected_permission(role, resource, action) is expected
