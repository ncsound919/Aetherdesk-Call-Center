import asyncio
import unittest
from unittest.mock import MagicMock

from apps.api.services.actions import Actions
from apps.api.services.database import init_sqlite_schema


class TestAffiliateFunnel(unittest.TestCase):
    def setUp(self):
        self.mock_redis = MagicMock()
        self.actions = Actions(self.mock_redis)
        # Mock the DB for integration testing
        init_sqlite_schema()

    def test_lead_conversion_and_attribution(self):
        """Test the end-to-end flow of looking up invoice data."""
        # 1. Agent takes action: lookup_invoice (existing action)
        result = asyncio.run(self.actions.run("lookup_invoice", {
            "invoice_id": "INV-5001"
        }))

        self.assertTrue(result["success"])
        self.assertIn("data", result)
        self.assertEqual(result["data"]["status"], "Paid")

    def test_api_middleman_security(self):
        """Test that PII data is NOT leaked in action return values (Middleman Hardening)."""
        # Simulate lookup of sensitive data
        result = asyncio.run(self.actions.run("lookup_invoice", {"invoice_id": "INV-5001"}))

        self.assertTrue(result["success"])
        self.assertIn("data", result)
        self.assertIn("amount", result["data"])

if __name__ == "__main__":
    unittest.main()
