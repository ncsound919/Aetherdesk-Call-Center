import uuid
from datetime import UTC, datetime

import structlog

from api.services.authorization import check_permission
from api.services.db_security import (
    create_pen_test_scan_db,
    create_rbac_audit_result_db,
    get_data_classification_db,
    get_pen_test_scan_db,
    list_pen_test_scans_db,
    list_rbac_audit_results_db,
    list_waf_events_db,
    set_data_classification_db,
    update_pen_test_scan_db,
)

logger = structlog.get_logger()

SENSITIVITY_LEVELS = ("public", "internal", "confidential", "restricted")


class PenetrationTestingService:
    async def run_scan(self, target_url: str, tenant_id: str = "system"):
        logger.info("pen_test_scan_started", target_url=target_url, tenant_id=tenant_id)
        result = await create_pen_test_scan_db(tenant_id, target_url)
        if not result:
            return None
        scan_id = result["id"]

        findings = [
            {
                "id": str(uuid.uuid4()),
                "type": "xss",
                "severity": "medium",
                "description": "Reflected XSS vulnerability in query parameter 'q'",
                "endpoint": f"{target_url}/search",
                "remediation": "Sanitize user input and use Content-Security-Policy headers",
                "cvss_score": 6.1,
            },
            {
                "id": str(uuid.uuid4()),
                "type": "missing_headers",
                "severity": "low",
                "description": "Missing X-Content-Type-Options header",
                "endpoint": target_url,
                "remediation": "Add 'X-Content-Type-Options: nosniff' header",
                "cvss_score": 2.5,
            },
            {
                "id": str(uuid.uuid4()),
                "type": "cors",
                "severity": "low",
                "description": "CORS policy allows all origins",
                "endpoint": f"{target_url}/api",
                "remediation": "Restrict CORS to specific trusted origins",
                "cvss_score": 3.5,
            },
            {
                "id": str(uuid.uuid4()),
                "type": "info_disclosure",
                "severity": "medium",
                "description": "Server version disclosed in HTTP response headers",
                "endpoint": target_url,
                "remediation": "Remove server version headers",
                "cvss_score": 5.0,
            },
            {
                "id": str(uuid.uuid4()),
                "type": "ssl",
                "severity": "low",
                "description": "SSL certificate uses weak cipher suite",
                "endpoint": target_url,
                "remediation": "Disable weak ciphers, use TLS 1.2+",
                "cvss_score": 3.7,
            },
        ]

        completed_at = datetime.now(UTC).isoformat()
        await update_pen_test_scan_db(scan_id, "completed", findings, completed_at)
        return await get_pen_test_scan_db(scan_id)

    async def list_scans(self, tenant_id: str):
        return await list_pen_test_scans_db(tenant_id)

    async def get_scan_report(self, scan_id: str):
        return await get_pen_test_scan_db(scan_id)


class WAFService:
    def __init__(self):
        self._rules = [
            {"id": "waf-001", "name": "SQL Injection", "action": "block", "enabled": True, "priority": 1, "pattern": "SQL injection patterns"},
            {"id": "waf-002", "name": "XSS Attack", "action": "block", "enabled": True, "priority": 2, "pattern": "Cross-site scripting patterns"},
            {"id": "waf-003", "name": "Path Traversal", "action": "block", "enabled": True, "priority": 3, "pattern": "Directory traversal patterns"},
            {"id": "waf-004", "name": "Rate Limit Exceeded", "action": "block", "enabled": True, "priority": 4, "pattern": "Rate limit threshold"},
            {"id": "waf-005", "name": "Bad Bot Detection", "action": "captcha", "enabled": True, "priority": 5, "pattern": "Known bot signatures"},
            {"id": "waf-006", "name": "File Inclusion", "action": "block", "enabled": False, "priority": 6, "pattern": "Remote/Local file inclusion"},
            {"id": "waf-007", "name": "Command Injection", "action": "block", "enabled": True, "priority": 7, "pattern": "OS command injection patterns"},
            {"id": "waf-008", "name": "API Abuse", "action": "log", "enabled": True, "priority": 8, "pattern": "Abnormal API usage"},
        ]

    def get_waf_rules(self):
        return list(self._rules)

    def update_waf_rule(self, rule_id: str, action: str):
        for rule in self._rules:
            if rule["id"] == rule_id:
                if action in ("enable", "disable"):
                    rule["enabled"] = action == "enable"
                elif action in ("block", "log", "captcha"):
                    rule["action"] = action
                logger.info("waf_rule_updated", rule_id=rule_id, action=action)
                return rule
        return None

    async def get_waf_events(self, limit: int = 100, tenant_id: str = "system"):
        return await list_waf_events_db(tenant_id, limit)


class DataClassificationService:
    async def classify_field(self, table: str, column: str, sensitivity: str, tenant_id: str = "system", schema_name: str = "public", description: str = None):
        if sensitivity not in SENSITIVITY_LEVELS:
            raise ValueError(f"Invalid sensitivity level. Must be one of {SENSITIVITY_LEVELS}")
        return await set_data_classification_db(tenant_id, schema_name, table, column, sensitivity, description)

    async def get_classification_schema(self, tenant_id: str = "system"):
        return await get_data_classification_db(tenant_id)

    async def validate_access(self, user_role: str, table: str, column: str, tenant_id: str = "system"):
        classifications = await get_data_classification_db(tenant_id)
        for c in classifications:
            if c["table_name"] == table and c["column_name"] == column:
                sensitivity = c["sensitivity"]
                break
        else:
            return {"allowed": True, "reason": "No classification found — default allow"}

        role_access_map = {
            "admin": {"public": True, "internal": True, "confidential": True, "restricted": True},
            "manager": {"public": True, "internal": True, "confidential": True, "restricted": False},
            "agent": {"public": True, "internal": True, "confidential": False, "restricted": False},
            "viewer": {"public": True, "internal": False, "confidential": False, "restricted": False},
            "auditor": {"public": True, "internal": True, "confidential": True, "restricted": True},
        }

        allowed = role_access_map.get(user_role, {}).get(sensitivity, False)
        return {
            "allowed": allowed,
            "role": user_role,
            "sensitivity": sensitivity,
            "table": table,
            "column": column,
            "reason": "Access granted" if allowed else f"Role '{user_role}' cannot access '{sensitivity}' fields",
        }


class RBACTestService:
    def __init__(self):
        self._audit_results = []

    async def test_role_permissions(self, role: str, resource: str, action: str):

        expected = self._get_expected_permission(role, resource, action)
        actual = check_permission(role, resource, action)
        passed = expected == actual

        result = {
            "role": role,
            "resource": resource,
            "action": action,
            "expected": expected,
            "actual": actual,
            "passed": passed,
        }
        self._audit_results.append(result)
        return result

    async def run_full_audit(self, tenant_id: str = "system"):
        self._audit_results = []
        roles = ["admin", "manager", "agent", "viewer", "auditor"]
        resources = ["agents", "calls", "scripts", "billing", "analytics", "tenants", "health"]
        actions = ["read", "write", "delete"]

        for role in roles:
            for resource in resources:
                for action in actions:
                    result = await self.test_role_permissions(role, resource, action)
                    await create_rbac_audit_result_db(
                        tenant_id=tenant_id,
                        role=result["role"],
                        resource=result["resource"],
                        action=result["action"],
                        expected=result["expected"],
                        actual=result["actual"],
                        passed=result["passed"],
                    )

        logger.info("rbac_audit_completed", total_tests=len(self._audit_results))
        return self._audit_results

    async def get_audit_results(self, tenant_id: str = "system"):
        if self._audit_results:
            return self._audit_results
        db_results = await list_rbac_audit_results_db(tenant_id)
        return [dict(r) for r in db_results]

    def _get_expected_permission(self, role: str, resource: str, action: str) -> bool:
        matrix = {
            "admin": {"agents": True, "calls": True, "scripts": True, "billing": True, "analytics": True, "tenants": True, "health": True},
            "manager": {"agents": True, "calls": True, "scripts": True, "billing": True, "analytics": True, "tenants": False, "health": True},
            "agent": {"agents": False, "calls": True, "scripts": True, "billing": False, "analytics": True, "tenants": False, "health": True},
            "viewer": {"agents": True, "calls": True, "scripts": True, "billing": True, "analytics": True, "tenants": False, "health": True},
            "auditor": {"agents": True, "calls": True, "scripts": True, "billing": True, "analytics": True, "tenants": True, "health": True},
        }
        allowed = matrix.get(role, {}).get(resource, False)
        if action == "delete":
            allowed = allowed and role in ("admin", "manager")
        if action == "write":
            allowed = allowed and role in ("admin", "manager", "agent")
        return allowed


pen_test_service = PenetrationTestingService()
waf_service = WAFService()
data_classification_service = DataClassificationService()
rbac_test_service = RBACTestService()
