import structlog

logger = structlog.get_logger()


class SupervisorService:
    async def get_wallboard_data(self, tenant_id):
        from api.services.db_calls import list_calls
        calls = await list_calls(tenant_id, limit=500)
        active_calls = [c for c in calls if c.get("call_status") in ("active", "ringing", "initiated")]
        waiting = [c for c in calls if c.get("call_status") == "queued"]

        from api.services.db_tenants import list_agents
        agents = await list_agents(tenant_id)
        online = [a for a in agents if a.get("status") in ("available", "online", "busy", "on_call")]
        offline = [a for a in agents if a.get("status") == "offline"]

        durations = [c.get("duration_seconds", 0) for c in active_calls]
        wait_times = [c.get("wait_time_seconds", 0) for c in waiting]

        return {
            "active_calls": len(active_calls),
            "waiting_queue": len(waiting),
            "agents_online": len(online),
            "agents_offline": len(offline),
            "agents_total": len(agents),
            "avg_wait_seconds": round(sum(wait_times) / len(wait_times), 1) if wait_times else 0,
            "longest_wait_seconds": max(wait_times) if wait_times else 0,
            "avg_call_duration_seconds": round(sum(durations) / len(durations), 1) if durations else 0,
        }

    async def get_live_agent_status(self, tenant_id):
        from api.services.db_tenants import list_agents
        agents = await list_agents(tenant_id)
        result = []
        for a in agents:
            result.append({
                "id": a.get("id"),
                "name": a.get("name"),
                "status": a.get("status"),
                "current_call_duration": a.get("current_call_duration", 0),
                "calls_today": a.get("total_calls", 0),
                "adherence_pct": a.get("adherence_pct", 0),
            })
        return result

    async def get_team_performance(self, tenant_id, period="7d"):
        from api.services.db_tenants import list_agents
        agents = await list_agents(tenant_id)
        team = []
        for a in agents:
            team.append({
                "agent_id": a.get("id"),
                "name": a.get("name"),
                "calls_handled": a.get("total_calls", 0),
                "avg_aht": round(a.get("total_talk_time_seconds", 0) / max(a.get("total_calls", 0), 1), 1),
                "csat": float(a.get("avg_rating", 0)),
                "status": a.get("status"),
            })
        return {"agents": team, "total_agents": len(team)}

    async def get_agent_detail(self, agent_id, period="7d"):
        from api.services.db_tenants import get_agent_db
        agent = await get_agent_db(agent_id)
        if not agent:
            return None
        return {
            "id": agent.get("id"),
            "name": agent.get("name"),
            "status": agent.get("status"),
            "total_calls": agent.get("total_calls", 0),
            "total_talk_time": agent.get("total_talk_time_seconds", 0),
            "avg_rating": float(agent.get("avg_rating", 0)),
            "skills": agent.get("skills", []),
        }

    async def get_recent_alerts(self, tenant_id):
        alerts = []
        wallboard = await self.get_wallboard_data(tenant_id)
        if wallboard["longest_wait_seconds"] > 300:
            alerts.append({
                "type": "sla_breach",
                "severity": "critical",
                "message": f"Longest wait time is {wallboard['longest_wait_seconds']}s — exceeds 5min SLA",
                "timestamp": None,
            })
        if wallboard["waiting_queue"] > 10:
            alerts.append({
                "type": "long_wait",
                "severity": "warning",
                "message": f"Queue depth is {wallboard['waiting_queue']} — consider adding agents",
                "timestamp": None,
            })
        if wallboard["agents_online"] < wallboard["agents_total"] * 0.5 and wallboard["agents_total"] > 0:
            alerts.append({
                "type": "agent_offline",
                "severity": "warning",
                "message": f"Only {wallboard['agents_online']}/{wallboard['agents_total']} agents online",
                "timestamp": None,
            })
        return alerts


supervisor_service = SupervisorService()
