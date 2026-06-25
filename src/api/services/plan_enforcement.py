"""Plan enforcement helpers.

Used by middleware/endpoints to check if a tenant has reached its plan
limit before allowing an action (creating an agent, starting a call, etc.).
"""
import logging

logger = logging.getLogger(__name__)


class PlanLimitExceeded(Exception):
    def __init__(self, message: str, current: int, limit: int, plan: str):
        super().__init__(message)
        self.message = message
        self.current = current
        self.limit = limit
        self.plan = plan


async def check_agent_limit(tenant_id: str) -> tuple[bool, dict]:
    """Check whether tenant can create a new agent."""
    from api.services.db_tenants import count_active_agents_db, get_tenant_plan_db

    plan = await get_tenant_plan_db(tenant_id)
    max_agents = (plan.get("max_agents") if plan else None) or 1
    current = await count_active_agents_db(tenant_id)

    if current >= max_agents:
        plan_name = (plan.get("plan_name") if plan else None) or "free"
        return False, {
            "error": "plan_limit_reached",
            "resource": "agents",
            "current": current,
            "limit": max_agents,
            "plan": plan_name,
            "message": f"Agent limit reached for {plan_name} plan ({current}/{max_agents}). Upgrade to add more.",
        }
    return True, {"current": current, "limit": max_agents}


async def check_call_limit(tenant_id: str) -> tuple[bool, dict]:
    """Check whether tenant can start a new call."""
    from api.services.db_tenants import count_active_calls_db, get_tenant_plan_db

    plan = await get_tenant_plan_db(tenant_id)
    max_calls = (plan.get("max_concurrent_calls") if plan else None) or 1
    current = await count_active_calls_db(tenant_id)

    if current >= max_calls:
        plan_name = (plan.get("plan_name") if plan else None) or "free"
        return False, {
            "error": "plan_limit_reached",
            "resource": "concurrent_calls",
            "current": current,
            "limit": max_calls,
            "plan": plan_name,
            "message": f"Concurrent call limit reached for {plan_name} plan ({current}/{max_calls}). Upgrade to add more.",
        }
    return True, {"current": current, "limit": max_calls}

