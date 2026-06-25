import uuid

import structlog

logger = structlog.get_logger()


class SMSService:
    """SMS service with Twilio API stub implementations."""

    async def send_sms(self, to_number, message, template_name=None, template_vars=None):
        sid = f"SM{uuid.uuid4().hex[:24]}"
        logger.info("sms_send_stub", to=to_number, template=template_name, sid=sid)
        return {
            "success": True,
            "sid": sid,
            "to": to_number,
            "body": message[:50],
            "status": "sent",
        }

    async def send_bulk_sms(self, recipients, message):
        results = []
        for to in recipients:
            sid = f"SM{uuid.uuid4().hex[:24]}"
            results.append({
                "success": True,
                "sid": sid,
                "to": to,
                "status": "sent",
            })
        logger.info("sms_bulk_stub", recipient_count=len(recipients))
        return {"success": True, "results": results, "total": len(results)}

    async def process_inbound_sms(self, from_number, body, session_id=None):
        logger.info("sms_inbound_stub", from_=from_number, body=body)
        return {
            "success": True,
            "from": from_number,
            "body": body,
            "session_id": session_id,
            "processed": True,
        }

    async def get_sms_templates(self, tenant_id):
        from api.services.db_omnichannel import list_sms_templates_db
        return await list_sms_templates_db(tenant_id)

    async def create_sms_template(self, tenant_id, name, body):
        from api.services.db_omnichannel import create_sms_template_db
        return await create_sms_template_db(tenant_id, name, body)

    async def get_sms_log(self, tenant_id, limit=100, offset=0):
        from api.services.db_omnichannel import list_sms_log_db
        return await list_sms_log_db(tenant_id, limit=limit, offset=offset)


sms_service = SMSService()
