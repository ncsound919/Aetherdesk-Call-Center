import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.actions import Actions
from api.services.orchestrator import ReActAgent


class TestAgenticReasoning(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Start patches
        self.db_patcher = patch("api.services.database.db_context")
        self.ao_patcher = patch("api.services.orchestrator.agentops")
        self.mem_patcher = patch("api.services.memory_service.memory_service.get_memories", new_callable=AsyncMock)
        self.mock_db = self.db_patcher.start()
        self.mock_ao = self.ao_patcher.start()
        self.mock_mem = self.mem_patcher.start()
        self.mock_mem.return_value = []

        self.mock_redis = MagicMock()
        self.actions = Actions(self.mock_redis)
        self.agent = ReActAgent(
            name="TestAgent",
            system_prompt="You are a helpful assistant.",
            tools=["lookup_invoice", "get_order_status"],
            actions=self.actions
        )
        # Mock DB for profile lookup
        mock_conn = self.mock_db.return_value.__enter__.return_value
        mock_conn.cursor.return_value.fetchone.return_value = {"parameters": "{}"}

    async def asyncTearDown(self):
        self.db_patcher.stop()
        self.ao_patcher.stop()
        self.mem_patcher.stop()

    @patch("httpx.AsyncClient.post")
    async def test_agent_selects_invoice_tool_for_billing_inquiry(self, mock_post):
        """Test if the agent correctly identifies a billing intent and uses the lookup_invoice tool."""
        # Mock LLM response to simulate tool call
        mock_response_1 = MagicMock()
        mock_response_1.status_code = 200
        mock_response_1.json.return_value = {
            "message": {
                "content": '{"thought": "Customer wants to know about an invoice.", "tool": "lookup_invoice", "tool_input": "INV-123"}'
            }
        }

        # Mock second response after tool result
        mock_response_2 = MagicMock()
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = {
            "message": {
                "content": '{"thought": "I have the info.", "response": "Your invoice INV-123 is paid."}'
            }
        }

        mock_post.side_effect = [mock_response_1, mock_response_2]

        # Mock tool execution
        with patch.object(self.actions, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"success": True, "data": {"status": "Paid"}}

            history = []
            user_input = "What is the status of my invoice INV-123?"

            response = await self.agent.step(history, user_input)

            # Verify tool was called
            mock_run.assert_called_with("lookup_invoice", {"invoice_id": "INV-123"}, tenant_id="TENANT-001")
            self.assertEqual(response.action_taken, "lookup_invoice")
            self.assertEqual(response.text, "Your invoice INV-123 is paid.")

    def test_agent_fingerprint_consistency(self):
        """Test if the agent response includes required telemetry fields (fingerprinting)."""
        pass

if __name__ == "__main__":
    unittest.main()
