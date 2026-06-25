import asyncio
import unittest
from unittest.mock import MagicMock, patch

from api.services.actions import Actions
from api.services.orchestrator import Orchestrator


class TestAutonomousSalesJourney(unittest.TestCase):
    @patch("httpx.AsyncClient.post")
    def test_full_sale_resolution_journey(self, mock_post):
        """Test a full journey from initial customer greeting to sales resolution."""
        # Setup
        mock_redis = MagicMock()
        actions = Actions(mock_redis)
        orch = Orchestrator(actions)

        # Responses for Supervisor and Agents
        supervisor_resp = MagicMock()
        supervisor_resp.status_code = 200
        supervisor_resp.json.return_value = {"message": {"content": '{"thought": "Routing to billing", "route_to": "billing"}'}}

        agent_resp_1 = MagicMock()
        agent_resp_1.status_code = 200
        agent_resp_1.json.return_value = {"message": {"content": '{"thought": "Inquiry", "response": "Our premium plan is $499.", "tool": null}'}}

        agent_resp_2 = MagicMock()
        agent_resp_2.status_code = 200
        agent_resp_2.json.return_value = {"message": {"content": '{"thought": "Buying", "tool": "process_payment", "tool_input": {"amount": 499}}'}}

        agent_resp_3 = MagicMock()
        agent_resp_3.status_code = 200
        agent_resp_3.json.return_value = {"message": {"content": '{"thought": "Done", "response": "Your order is confirmed.", "tool": null}'}}

        # Configure side effect for sequential calls
        mock_post.side_effect = [supervisor_resp, agent_resp_1, agent_resp_2, agent_resp_3]

        history = []
        session_state = {}

        # Turn 1
        user_input = "Hi, I heard about AetherDesk. How much is it?"
        response_1 = asyncio.run(orch.step(session_state, history, user_input))
        self.assertIn("$499", response_1.text)

        # Turn 2 (Now session_state['active_agent'] is 'billing', so supervisor is NOT called)
        user_input_2 = "That sounds great. Let's do it."
        response_2 = asyncio.run(orch.step(session_state, history, user_input_2))
        self.assertEqual(response_2.action_taken, "process_payment")

if __name__ == "__main__":
    unittest.main()
