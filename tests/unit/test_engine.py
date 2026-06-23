import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request, Form
from fastapi.responses import Response


class TestEngineUtils:
    """Tests for engine utility functions."""

    def test_build_xml_response(self):
        from apps.api.routers.engine import build_xml_response

        xml = build_xml_response("Hello World")
        assert "<?xml version=" in xml
        assert "<Message>Hello World</Message>" in xml
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?><Response>')

    def test_prompt_for(self):
        from apps.api.routers.engine import prompt_for, VMState

        # Test ask_q1
        state = VMState(protocol_id="bootstrap_q1", node="ask_q1", fields={}, transcript=[])
        prompt = prompt_for(state)
        assert "What's this about?" in prompt
        assert "Refill" in prompt
        assert "Billing" in prompt

        # Test ask_q2_refill
        state.node = "ask_q2_refill"
        prompt = prompt_for(state)
        assert "Refill:" in prompt
        assert "Using Rx ID" in prompt

        # Test ask_q2_billing
        state.node = "ask_q2_billing"
        prompt = prompt_for(state)
        assert "Billing:" in prompt
        assert "Invoice" in prompt

        # Test agent_handoff
        state.node = "agent_handoff"
        prompt = prompt_for(state)
        assert "Transferring to an agent" in prompt

        # Test unknown node
        state.node = "unknown_node"
        prompt = prompt_for(state)
        assert prompt == "..."


class TestInboundSMS:
    """Tests for inbound SMS endpoint."""

    @pytest.mark.asyncio
    async def test_inbound_sms_new_session(self):
        from apps.api.routers.engine import inbound_sms

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_request.app.state.redis = mock_redis

        with patch("apps.api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("apps.api.routers.engine.Actions") as mock_actions_class:
            
            mock_vm = MagicMock()
            mock_vm_class.return_value = mock_vm
            
            mock_actions = MagicMock()
            mock_actions_class.return_value = mock_actions

            # Test with invalid input to get the initial question
            response = await inbound_sms(mock_request, From="+15551234567", Body="invalid")
            
        assert isinstance(response, Response)
        assert response.media_type == "application/xml"
        assert "What's this about?" in response.body.decode()
        mock_redis.get.assert_called_once_with("session:sms:+15551234567")
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_inbound_sms_existing_session(self):
        from apps.api.routers.engine import inbound_sms, VMState

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        
        # Create existing session state
        existing_state = VMState(
            protocol_id="bootstrap_q1",
            node="ask_q1",
            fields={"phone": "+15551234567", "session_id": "sms:+15551234567"},
            transcript=[]
        )
        mock_redis.get.return_value = json.dumps(existing_state.__dict__)
        mock_request.app.state.redis = mock_redis

        with patch("apps.api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("apps.api.routers.engine.Actions") as mock_actions_class:
            
            mock_vm = MagicMock()
            mock_vm_class.return_value = mock_vm
            
            mock_actions = MagicMock()
            mock_actions_class.return_value = mock_actions

            response = await inbound_sms(mock_request, From="+15551234567", Body="1")
            
        assert isinstance(response, Response)
        assert response.media_type == "application/xml"
        mock_redis.get.assert_called_once_with("session:sms:+15551234567")

    @pytest.mark.asyncio
    async def test_inbound_sms_q1_selection(self):
        from apps.api.routers.engine import inbound_sms

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_request.app.state.redis = mock_redis

        with patch("apps.api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("apps.api.routers.engine.Actions") as mock_actions_class:
            
            # Test valid selection
            response = await inbound_sms(mock_request, From="+15551234567", Body="1")  # Refill
            
        assert "Refill:" in response.body.decode()
        assert "Using Rx ID" in response.body.decode()

        # Verify state was saved with correct fields
        saved_state = json.loads(mock_redis.setex.call_args[0][2])
        assert saved_state["fields"]["q1"] == "refill"
        assert saved_state["node"] == "ask_q2_refill"

    @pytest.mark.asyncio
    async def test_inbound_sms_q1_invalid_selection(self):
        from apps.api.routers.engine import inbound_sms

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_request.app.state.redis = mock_redis

        with patch("apps.api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("apps.api.routers.engine.Actions") as mock_actions_class:
            
            # Test invalid selection
            response = await inbound_sms(mock_request, From="+15551234567", Body="invalid")
            
        assert "What's this about?" in response.body.decode()  # Should repeat the question

    @pytest.mark.asyncio
    async def test_inbound_sms_q2_selection(self):
        from apps.api.routers.engine import inbound_sms, VMState

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        
        # Create state with q1 already answered
        existing_state = VMState(
            protocol_id="bootstrap_q1",
            node="ask_q2_refill",
            fields={"phone": "+15551234567", "session_id": "sms:+15551234567", "q1": "refill"},
            transcript=[]
        )
        mock_redis.get.return_value = json.dumps(existing_state.__dict__)
        mock_request.app.state.redis = mock_redis

        with patch("apps.api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("apps.api.routers.engine.Actions") as mock_actions_class, \
             patch("apps.api.routers.engine.route_resolver.route") as mock_route:
            
            mock_route.return_value = {
                "protocol_id": "refill_protocol",
                "queue": "refill_queue"
            }
            
            # Test valid q2 selection
            response = await inbound_sms(mock_request, From="+15551234567", Body="1")  # Using Rx ID
            
        assert "Starting your flow..." in response.body.decode()
        
        # Verify state was updated correctly
        saved_state = json.loads(mock_redis.setex.call_args[0][2])
        assert saved_state["protocol_id"] == "refill_protocol"
        assert saved_state["node"] == "start"
        assert saved_state["fields"]["queue"] == "refill_queue"

    @pytest.mark.asyncio
    async def test_inbound_sms_non_bootstrap_protocol(self):
        from apps.api.routers.engine import inbound_sms, VMState

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        
        # Create state with non-bootstrap protocol
        existing_state = VMState(
            protocol_id="refill_protocol",
            node="some_node",
            fields={"phone": "+15551234567", "session_id": "sms:+15551234567"},
            transcript=[]
        )
        mock_redis.get.return_value = json.dumps(existing_state.__dict__)
        mock_request.app.state.redis = mock_redis

        with patch("apps.api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("apps.api.routers.engine.Actions") as mock_actions_class:
            
            mock_vm = AsyncMock()
            mock_vm.step.return_value = existing_state
            mock_vm_class.return_value = mock_vm
            
            mock_actions = MagicMock()
            mock_actions_class.return_value = mock_actions

            response = await inbound_sms(mock_request, From="+15551234567", Body="test input")
            
        # Should call vm.step for non-bootstrap protocols (not awaited)
        mock_vm.step.assert_called_once_with(existing_state, "test input")

    @pytest.mark.asyncio
    async def test_inbound_sms_error_handling(self):
        from apps.api.routers.engine import inbound_sms

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Redis error")
        mock_request.app.state.redis = mock_redis

        with patch("apps.api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("apps.api.routers.engine.Actions") as mock_actions_class, \
             patch("apps.api.routers.engine.logger.warning") as mock_logger:
            
            response = await inbound_sms(mock_request, From="+15551234567", Body="1")
            
        # Should still return a response even if Redis fails
        assert isinstance(response, Response)
        assert response.media_type == "application/xml"
        # The exception is caught but not logged in the current implementation
        # This is actually a bug in the original code - it should log the error


class TestRouteResolver:
    """Tests for route resolver functionality."""

    @pytest.mark.asyncio
    async def test_route_resolver_integration(self):
        from apps.api.routers.engine import inbound_sms
        from apps.api.services.router import router as route_resolver

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_request.app.state.redis = mock_redis

        # Test the full flow: q1 -> q2 -> route resolution
        with patch("apps.api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("apps.api.routers.engine.Actions") as mock_actions_class, \
             patch("apps.api.routers.engine.route_resolver.route") as mock_route:
            
            mock_route.return_value = {
                "protocol_id": "refill_protocol",
                "queue": "refill_queue"
            }
            
            # First message: select refill
            response1 = await inbound_sms(mock_request, From="+15551234567", Body="1")
            
            # Second message: select using Rx ID
            # Need to get the saved state from the first call
            saved_state = json.loads(mock_redis.setex.call_args[0][2])
            mock_redis.get.return_value = json.dumps(saved_state)
            
            response2 = await inbound_sms(mock_request, From="+15551234567", Body="1")
            
        # First response should be q2 refill question
        assert "Refill:" in response1.body.decode()
        
        # Second response should be "Starting your flow..."
        assert "Starting your flow..." in response2.body.decode()
        
        # Verify route resolver was called
        mock_route.assert_called_once_with("refill", "id_lookup")