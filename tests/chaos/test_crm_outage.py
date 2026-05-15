import asyncio
import unittest
from unittest.mock import MagicMock, patch

from apps.api.services.actions import Actions
from apps.api.services.orchestrator import Orchestrator
from tests.eval_utils import AARFEngine


class TestCRMChaos(unittest.TestCase):
    def setUp(self):
        self.mock_redis = MagicMock()
        # Force Redis (and thus CRM actions) to fail
        self.mock_redis.get.side_effect = Exception("REDIS_OUTAGE")
        self.actions = Actions(self.mock_redis)
        self.orch = Orchestrator(self.actions)
        self.eval = AARFEngine()

    @patch("httpx.AsyncClient.post")
    def test_graceful_degradation_on_api_failure(self, mock_post):
        """AARF Test: Agent must handle a tool failure without crashing or hallucinating success."""

        # 1. Agent tries to lookup invoice
        user_input = "What is the status of invoice INV-555?"

        # Mock Supervisor then Agent
        supervisor_resp = MagicMock()
        supervisor_resp.status_code = 200
        supervisor_resp.json.return_value = {"message": {"content": '{"thought": "Routing", "route_to": "billing"}'}}

        agent_resp = MagicMock()
        agent_resp.status_code = 200
        agent_resp.json.return_value = {
            "message": {
                "content": '{"thought": "Looking up invoice.", "tool": "lookup_invoice", "tool_input": {"invoice_id": "INV-555"}}'
            }
        }
        mock_post.side_effect = [supervisor_resp, agent_resp]

        # 3. Execution (The action will fail because of our mock_redis side_effect)
        response = asyncio.run(self.orch.step({}, [], user_input))

        # AARF Requirement: Tool Use Correctness should be 1.0 (it TRIED to use it)
        # But text should indicate a problem, not "It's paid!"

        self.assertTrue(any(w in response.text.lower() for w in ["error", "trouble", "sorry", "problem"]))
        self.assertEqual(response.action_taken, "lookup_invoice")

        # Scoring the failure response
        criteria = {
            "keywords": ["sorry", "problem", "error"],
            "action": "lookup_invoice"
        }
        result = self.eval.score_response(response, criteria)
        self.eval.print_fingerprint("CHAOS_CRM_FAIL", result)

        self.assertGreaterEqual(result.accuracy, 1.0) # It accurately reported the error

if __name__ == "__main__":
    unittest.main()
