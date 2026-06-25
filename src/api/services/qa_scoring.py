import json

import structlog

logger = structlog.get_logger()


class QAScore:
    def __init__(self):
        self.default_criteria = [
            {"name": "greeting", "description": "Professional greeting", "weight": 15},
            {"name": "listening", "description": "Active listening skills", "weight": 20},
            {"name": "knowledge", "description": "Product/service knowledge", "weight": 20},
            {"name": "resolution", "description": "Issue resolution effectiveness", "weight": 25},
            {"name": "closing", "description": "Professional closing and follow-up", "weight": 10},
            {"name": "compliance", "description": "Script and policy compliance", "weight": 10},
        ]

    async def score_call(self, tenant_id, call_id, agent_id, reviewer_id, rubric_id, scores_per_criterion: dict, notes=None) -> dict:
        from api.services.db_wfm import create_qa_score_db
        return await create_qa_score_db(
            tenant_id, call_id, agent_id, reviewer_id, rubric_id, scores_per_criterion, notes
        )

    async def get_agent_summary(self, agent_id) -> dict:
        from api.services.db_wfm import get_agent_qa_summary_db
        return await get_agent_qa_summary_db(agent_id)

    async def get_tenant_stats(self, tenant_id) -> dict:
        from api.services.db_wfm import list_qa_scores_db

        scores = await list_qa_scores_db(tenant_id, limit=10000)
        if not scores:
            return {
                "avg_score": 0.0,
                "total_reviewed": 0,
                "score_distribution": {},
                "top_issues": [],
            }

        total = len(scores)
        avg = sum(s.get("total_score", 0) for s in scores) / total if total else 0

        # Score distribution (buckets: 0-20, 20-40, 40-60, 60-80, 80-100)
        distribution = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
        for s in scores:
            sc = s.get("total_score", 0)
            if sc < 20:
                distribution["0-20"] += 1
            elif sc < 40:
                distribution["20-40"] += 1
            elif sc < 60:
                distribution["40-60"] += 1
            elif sc < 80:
                distribution["60-80"] += 1
            else:
                distribution["80-100"] += 1

        # Top issues: criteria with lowest average scores
        criteria_totals = {}
        criteria_counts = {}
        for s in scores:
            spc = s.get("scores_per_criterion", {})
            if isinstance(spc, str):
                try:
                    spc = json.loads(spc)
                except (json.JSONDecodeError, TypeError):
                    spc = {}
            if isinstance(spc, dict):
                for k, v in spc.items():
                    criteria_totals[k] = criteria_totals.get(k, 0) + v
                    criteria_counts[k] = criteria_counts.get(k, 0) + 1

        issues = []
        for k in criteria_totals:
            avg_val = criteria_totals[k] / criteria_counts[k] if criteria_counts[k] else 0
            if avg_val < 3.0:
                issues.append({"criterion": k, "avg_score": round(avg_val, 2)})
        issues.sort(key=lambda x: x["avg_score"])

        return {
            "avg_score": round(avg, 2),
            "total_reviewed": total,
            "score_distribution": distribution,
            "top_issues": issues[:5],
        }


qa_engine = QAScore()
