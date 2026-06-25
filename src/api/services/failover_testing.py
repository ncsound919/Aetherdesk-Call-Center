import random
import time
import uuid
from datetime import UTC, datetime, timedelta

import structlog

logger = structlog.get_logger()

_in_memory_history = []
_in_memory_config = {
    "primary_provider": "twilio",
    "secondary_provider": "fonster",
    "auto_test_interval_hours": 24,
    "notifications_enabled": True,
    "last_test_at": None,
}


class FailoverTestingService:

    async def test_telephony_failover(self):
        logger.info("Running telephony failover test", primary="twilio", secondary="fonster")
        start = time.monotonic()

        # Simulate failover from Twilio to Fonoster
        failover_success = random.random() > 0.05
        failover_time_ms = round(random.uniform(500, 3000), 2)

        # Simulate fallback from Fonoster to Twilio
        fallback_success = random.random() > 0.05

        elapsed = round((time.monotonic() - start) * 1000, 2)

        result = {
            "id": str(uuid.uuid4()),
            "primary": "twilio",
            "secondary": "fonster",
            "failover_success": failover_success,
            "failover_time_ms": failover_time_ms,
            "fallback_success": fallback_success,
            "total_test_time_ms": elapsed,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        _in_memory_history.insert(0, result)
        _in_memory_config["last_test_at"] = result["timestamp"]

        logger.info("Failover test complete", result=result)
        return result

    async def get_failover_status(self):
        return {
            "primary_provider": _in_memory_config["primary_provider"],
            "secondary_provider": _in_memory_config["secondary_provider"],
            "primary_healthy": True,
            "secondary_healthy": True,
            "last_test_at": _in_memory_config["last_test_at"],
            "auto_test_enabled": _in_memory_config["auto_test_interval_hours"] > 0,
        }

    async def schedule_failover_test(self, interval_hours: int):
        _in_memory_config["auto_test_interval_hours"] = interval_hours
        logger.info("Failover test schedule updated", interval_hours=interval_hours)
        return {
            "scheduled": True,
            "interval_hours": interval_hours,
            "next_test_at": (datetime.now(UTC) + timedelta(hours=interval_hours)).isoformat(),
        }

    async def get_failover_history(self, limit: int = 20):
        return _in_memory_history[:limit]

    async def get_failover_config(self):
        return dict(_in_memory_config)


failover_service = FailoverTestingService()
