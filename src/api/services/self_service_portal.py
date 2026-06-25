import uuid
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger()

_in_memory_complaints = []
_in_memory_callbacks = []
_in_memory_portal_data: dict[str, dict] = {}


class SelfServicePortalService:

    async def get_customer_portal_data(self, customer_id: str) -> dict:
        logger.info("Fetching customer portal data", customer_id=customer_id)

        if customer_id in _in_memory_portal_data:
            return _in_memory_portal_data[customer_id]

        return {
            "customer_id": customer_id,
            "call_history": [
                {"call_id": "CL-001", "date": "2025-06-20T10:30:00Z", "direction": "inbound",
                 "duration_seconds": 245, "status": "completed", "agent": "AI Agent Alpha"},
                {"call_id": "CL-002", "date": "2025-06-19T14:15:00Z", "direction": "outbound",
                 "duration_seconds": 180, "status": "completed", "agent": "AI Agent Beta"},
                {"call_id": "CL-003", "date": "2025-06-18T09:00:00Z", "direction": "inbound",
                 "duration_seconds": 320, "status": "missed", "agent": None},
            ],
            "invoices": [
                {"id": "INV-001", "date": "2025-06-01", "amount": 149.00, "status": "paid",
                 "description": "Monthly subscription — Pro plan"},
                {"id": "INV-002", "date": "2025-05-01", "amount": 149.00, "status": "paid",
                 "description": "Monthly subscription — Pro plan"},
                {"id": "INV-003", "date": "2025-04-01", "amount": 149.00, "status": "paid",
                 "description": "Monthly subscription — Pro plan"},
            ],
            "csat_scores": [
                {"call_id": "CL-001", "rating": 5, "feedback": "Great support!", "date": "2025-06-20"},
                {"call_id": "CL-002", "rating": 4, "feedback": "Helpful but took a bit long", "date": "2025-06-19"},
            ],
            "average_csat": 4.5,
            "preferences": {
                "communication_email": True,
                "communication_sms": True,
                "communication_phone": True,
                "marketing_emails": False,
                "callback_preference": "anytime",
                "timezone": "America/New_York",
            },
        }

    async def preview_call_recording(self, call_id: str) -> dict:
        return {
            "call_id": call_id,
            "recording_url": f"https://storage.aetherdesk.com/recordings/{call_id}.mp3",
            "duration_seconds": 245,
            "format": "mp3",
            "file_size_bytes": 3_850_000,
            "transcript_available": True,
            "preview_url": f"https://storage.aetherdesk.com/recordings/{call_id}_preview.mp3",
        }

    async def submit_complaint(self, customer_id: str, subject: str, description: str) -> dict:
        complaint = {
            "id": str(uuid.uuid4()),
            "customer_id": customer_id,
            "subject": subject,
            "description": description,
            "status": "open",
            "created_at": datetime.now(UTC).isoformat(),
        }
        _in_memory_complaints.append(complaint)
        logger.info("Complaint submitted", complaint_id=complaint["id"])
        return complaint

    async def schedule_call_back(self, customer_id: str, preferred_time: str, reason: str) -> dict:
        callback = {
            "id": str(uuid.uuid4()),
            "customer_id": customer_id,
            "preferred_time": preferred_time,
            "reason": reason,
            "status": "scheduled",
            "created_at": datetime.now(UTC).isoformat(),
        }
        _in_memory_callbacks.append(callback)
        logger.info("Callback scheduled", callback_id=callback["id"])
        return callback

    async def get_billing_history(self, customer_id: str) -> list[dict]:
        data = await self.get_customer_portal_data(customer_id)
        return data.get("invoices", [])

    async def update_preferences(self, customer_id: str, preferences: dict) -> dict:
        allowed_keys = {"communication_email", "communication_sms", "communication_phone",
                        "marketing_emails", "callback_preference", "timezone"}
        filtered = {k: v for k, v in preferences.items() if k in allowed_keys}
        logger.info("Preferences updated", customer_id=customer_id, preferences=filtered)
        return {"customer_id": customer_id, "preferences": filtered, "updated_at": datetime.now(UTC).isoformat()}


self_service_portal_service = SelfServicePortalService()
