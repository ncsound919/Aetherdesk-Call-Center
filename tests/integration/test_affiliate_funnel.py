import unittest
from unittest.mock import MagicMock

from apps.api.services.actions import Actions
from apps.api.services.database import init_db


class TestAffiliateFunnel(unittest.TestCase):
    def setUp(self):
        self.mock_redis = MagicMock()
        self.actions = Actions(self.mock_redis)
        # Mock the DB for integration testing
        init_db()

    def test_lead_conversion_and_attribution(self):
        """Test the end-to-end flow of attributing a sale to an affiliate."""
        # 1. Simulate agent resolving a call with a successful sale
        _call_context = {
            "session_id": "call_test_affiliate",
            "affiliate_id": "AFF-99",
            "customer_email": "buyer@example.com"
        }

        # 2. Agent takes action: process_payment
        result = self.actions.run("process_payment", {
            "amount": 499.00,
            "description": "Premium Aether License",
            "affiliate_id": "AFF-99"
        })

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["affiliate_id"], "AFF-99")
        self.assertEqual(result["data"]["commission_status"], "Pending")

    def test_api_middleman_security(self):
        """Test that PII data is NOT leaked in action return values (Middleman Hardening)."""
        # Simulate lookup of sensitive data
        result = self.actions.run("lookup_invoice", {"invoice_id": "INV-1001"})

        # Ensure the raw encrypted field is not present in the final JSON output
        # (Only decrypted display values should be returned)
        self.assertNotIn("raw_pii", result["data"])
        self.assertIn("amount", result["data"])

if __name__ == "__main__":
    unittest.main()
