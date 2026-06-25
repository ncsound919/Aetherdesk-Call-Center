import json
import uuid

import structlog

from api.services.db_config import USE_POSTGRES
from api.services.db_pool import _get_sqlite_conn, get_pg_pool

logger = structlog.get_logger()

VERTICALS = {
    "healthcare": {
        "id": "healthcare",
        "name": "Healthcare",
        "description": "HIPAA-compliant patient communication — appointment reminders, prescription refills, patient intake",
        "icon": "Stethoscope",
        "compliance": ["HIPAA", "HITECH", "PCI-DSS"],
        "intents": [
            "appointment_reminder", "appointment_scheduling", "prescription_refill",
            "patient_intake", "lab_results", "insurance_verification", "billing_inquiry"
        ],
        "script_templates": ["TPL-HEALTHCARE"],
        "compliance_rules": {
            "require_consent": True,
            "encryption_required": True,
            "audit_logging": True,
            "data_retention_days": 2555,
            "baa_required": True,
            "hipaa_consent_required": True,
        },
        "routing_config": {
            "priority_intents": ["appointment_reminder", "prescription_refill"],
            "escalation_intents": ["billing_inquiry", "insurance_verification"],
        },
        "required_integrations": ["ehr_system", "pharmacy_system", "hipaa_compliance"],
    },
    "finance/debt_collection": {
        "id": "finance/debt_collection",
        "name": "Finance & Debt Collection",
        "description": "Regulation F-compliant collection — payment arrangements, dispute handling, validation notices",
        "icon": "DollarSign",
        "compliance": ["FDCPA", "Regulation F", "TCPA", "FCRA", "CCPA"],
        "intents": [
            "payment_arrangement", "dispute_handling", "validation_notice",
            "settlement_offer", "payment_confirmation", "account_inquiry", "cease_and_desist"
        ],
        "script_templates": ["TPL-DEBT"],
        "compliance_rules": {
            "require_consent": True,
            "call_time_restrictions": True,
            "max_call_attempts": 3,
            "validation_notice_required": True,
            "dispute_escalation": True,
            "audio_disclosure_required": True,
        },
        "routing_config": {
            "priority_intents": ["payment_arrangement"],
            "escalation_intents": ["dispute_handling", "cease_and_desist"],
        },
        "required_integrations": ["payment_processor", "credit_bureau", "collections_system"],
    },
    "real_estate": {
        "id": "real_estate",
        "name": "Real Estate",
        "description": "Property inquiry management — showing scheduling, follow-up automation, lead qualification",
        "icon": "Building2",
        "compliance": ["TCPA", "CAN-SPAM", "NAR_ethics"],
        "intents": [
            "property_inquiry", "showing_scheduling", "follow_up",
            "lead_qualification", "offer_discussion", "market_analysis", "referral"
        ],
        "script_templates": ["TPL-REAL-ESTATE"],
        "compliance_rules": {
            "require_consent": False,
            "dnc_scrubbing": True,
            "disclosure_required": True,
        },
        "routing_config": {
            "priority_intents": ["property_inquiry", "showing_scheduling"],
            "escalation_intents": ["offer_discussion"],
        },
        "required_integrations": ["mls_system", "crm", "calendar_sync"],
    },
    "ecommerce": {
        "id": "ecommerce",
        "name": "E-Commerce",
        "description": "Customer order management — order status, return processing, shipping updates, abandoned cart recovery",
        "icon": "ShoppingCart",
        "compliance": ["TCPA", "CAN-SPAM", "PCI-DSS"],
        "intents": [
            "order_status", "return_initiation", "shipping_update",
            "abandoned_cart_recovery", "product_inquiry", "refund_status", "feedback_collection"
        ],
        "script_templates": ["TPL-SUPPORT"],
        "compliance_rules": {
            "require_consent": False,
            "dnc_scrubbing": True,
            "order_verification_required": True,
        },
        "routing_config": {
            "priority_intents": ["order_status", "shipping_update"],
            "escalation_intents": ["refund_status"],
        },
        "required_integrations": ["shopify", "order_management", "shipping_provider"],
    },
}


class VerticalTemplatesService:

    def get_verticals(self):
        return [
            {
                "id": v["id"],
                "name": v["name"],
                "description": v["description"],
                "icon": v["icon"],
                "compliance": v["compliance"],
                "intent_count": len(v["intents"]),
                "script_count": len(v["script_templates"]),
            }
            for v in VERTICALS.values()
        ]

    def get_vertical_config(self, vertical_id):
        vertical = VERTICALS.get(vertical_id)
        if not vertical:
            return None
        return vertical

    def get_vertical_compliance(self, vertical_id):
        vertical = VERTICALS.get(vertical_id)
        if not vertical:
            return None
        return {
            "vertical_id": vertical_id,
            "name": vertical["name"],
            "compliance_standards": vertical["compliance"],
            "compliance_rules": vertical["compliance_rules"],
        }

    def get_vertical_scripts(self, vertical_id):
        vertical = VERTICALS.get(vertical_id)
        if not vertical:
            return None
        return {
            "vertical_id": vertical_id,
            "name": vertical["name"],
            "script_templates": vertical["script_templates"],
            "intents": vertical["intents"],
        }

    async def apply_vertical_template(self, tenant_id, vertical_id):
        vertical = VERTICALS.get(vertical_id)
        if not vertical:
            return None
        deployment_id = str(uuid.uuid4())
        config_json = json.dumps(vertical)

        if USE_POSTGRES:
            pool = await get_pg_pool()
            if pool:
                await pool.execute("""
                    INSERT INTO vertical_deployments (id, tenant_id, vertical_id, status, config_json, created_at)
                    VALUES ($1, $2, $3, 'active', $4::jsonb, NOW())
                """, deployment_id, tenant_id, vertical_id, config_json)
                row = await pool.fetchrow("SELECT * FROM vertical_deployments WHERE id = $1", deployment_id)
                result = dict(row) if row else None
        else:
            conn = _get_sqlite_conn()
            try:
                now = __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()
                conn.execute("""
                    INSERT INTO vertical_deployments (id, tenant_id, vertical_id, status, config_json, created_at)
                    VALUES (?, ?, ?, 'active', ?, ?)
                """, (deployment_id, tenant_id, vertical_id, config_json, now))
                conn.commit()
                row = conn.execute("SELECT * FROM vertical_deployments WHERE id = ?", (deployment_id,)).fetchone()
                result = dict(row) if row else None
            finally:
                conn.close()

        logger.info("vertical_template_applied", tenant_id=tenant_id, vertical_id=vertical_id)
        return result


vertical_templates_service = VerticalTemplatesService()
