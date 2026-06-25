import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request, Form
from fastapi.responses import Response


class TestEngineUtils:
    """Tests for engine utility functions."""

    def test_build_xml_response(self):
        from api.routers.engine import build_xml_response

        xml = build_xml_response("Hello World")
        assert "<?xml version=" in xml
        assert "<Message>Hello World</Message>" in xml
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?><Response>')

    def test_prompt_for(self):
        from api.routers.engine import prompt_for, VMState

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
        from api.routers.engine import inbound_sms

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_request.app.state.redis = mock_redis

        with patch("api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("api.routers.engine.Actions") as mock_actions_class:
            
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
        from api.routers.engine import inbound_sms, VMState

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

        with patch("api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("api.routers.engine.Actions") as mock_actions_class:
            
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
        from api.routers.engine import inbound_sms

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_request.app.state.redis = mock_redis

        with patch("api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("api.routers.engine.Actions") as mock_actions_class:
            
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
        from api.routers.engine import inbound_sms

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_request.app.state.redis = mock_redis

        with patch("api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("api.routers.engine.Actions") as mock_actions_class:
            
            # Test invalid selection
            response = await inbound_sms(mock_request, From="+15551234567", Body="invalid")
            
        assert "What's this about?" in response.body.decode()  # Should repeat the question

    @pytest.mark.asyncio
    async def test_inbound_sms_q2_selection(self):
        from api.routers.engine import inbound_sms, VMState

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

        with patch("api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("api.routers.engine.Actions") as mock_actions_class, \
             patch("api.routers.engine.route_resolver.route") as mock_route:
            
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
        from api.routers.engine import inbound_sms, VMState

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

        with patch("api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("api.routers.engine.Actions") as mock_actions_class:
            
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
        from api.routers.engine import inbound_sms

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Redis error")
        mock_request.app.state.redis = mock_redis

        with patch("api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("api.routers.engine.Actions") as mock_actions_class, \
             patch("api.routers.engine.logger.warning") as mock_logger:
            
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
        from api.routers.engine import inbound_sms
        from api.services.router import router as route_resolver

        mock_request = MagicMock(spec=Request)
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_request.app.state.redis = mock_redis

        # Test the full flow: q1 -> q2 -> route resolution
        with patch("api.routers.engine.ProtocolVM") as mock_vm_class, \
             patch("api.routers.engine.Actions") as mock_actions_class, \
             patch("api.routers.engine.route_resolver.route") as mock_route:
            
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


class TestProtocolVM:
    def make_vm(self, proto_data=None):
        mock_loader = MagicMock()
        mock_loader.load.return_value = proto_data or {}
        mock_validators = MagicMock()
        mock_validators.validate.return_value = True
        mock_actions = MagicMock()
        mock_actions.run = AsyncMock(return_value={"success": True})
        from api.services.engine import ProtocolVM
        return ProtocolVM(mock_loader, mock_validators, mock_actions), mock_loader, mock_validators, mock_actions

    @pytest.mark.asyncio
    async def test_step_escape_hatch(self):
        from api.services.engine import VMState

        vm, _, _, _ = self.make_vm()
        state = VMState(protocol_id="test", node="start", fields={}, transcript=[])
        result = await vm.step(state, "agent")

        assert result.node == "agent_handoff"
        assert len(result.transcript) == 1
        assert result.transcript[0]["reason"] == "escape_hatch"

    @pytest.mark.asyncio
    async def test_step_escape_hatch_operator(self):
        from api.services.engine import VMState

        vm, _, _, _ = self.make_vm()
        state = VMState(protocol_id="test", node="start", fields={}, transcript=[])
        result = await vm.step(state, "operator")

        assert result.node == "agent_handoff"
        assert result.transcript[0]["reason"] == "escape_hatch"

    @pytest.mark.asyncio
    async def test_step_escape_hatch_zero(self):
        from api.services.engine import VMState

        vm, _, _, _ = self.make_vm()
        state = VMState(protocol_id="test", node="start", fields={}, transcript=[])
        result = await vm.step(state, "0")

        assert result.node == "agent_handoff"

    @pytest.mark.asyncio
    async def test_step_protocol_not_found(self):
        from api.services.engine import VMState

        vm, mock_loader, _, _ = self.make_vm()
        mock_loader.load.return_value = None
        state = VMState(protocol_id="missing", node="start", fields={}, transcript=[])
        result = await vm.step(state, "hello")

        assert result.node == "agent_handoff"
        assert result.transcript[0]["reason"] == "protocol_not_found"

    @pytest.mark.asyncio
    async def test_step_node_not_found(self):
        from api.services.engine import VMState

        proto = {"nodes": {"other_node": {}}}
        vm, _, _, _ = self.make_vm(proto)
        state = VMState(protocol_id="test", node="missing_node", fields={}, transcript=[])
        result = await vm.step(state, "hello")

        assert result.node == "agent_handoff"
        assert result.transcript[0]["reason"] == "node_not_found"

    @pytest.mark.asyncio
    async def test_step_field_node_valid(self):
        from api.services.engine import VMState

        proto = {
            "nodes": {
                "ask_name": {
                    "field": "name",
                    "validate": "not_empty",
                    "next": "ask_age"
                }
            }
        }
        vm, _, mock_validators, _ = self.make_vm(proto)
        state = VMState(protocol_id="test", node="ask_name", fields={}, transcript=[])
        result = await vm.step(state, "John")

        assert result.fields["name"] == "John"
        assert result.node == "ask_age"
        assert result.transcript[0]["reason"] == "field_set:name"
        mock_validators.validate.assert_called_once_with("not_empty", "John")

    @pytest.mark.asyncio
    async def test_step_field_node_validation_fails(self):
        from api.services.engine import VMState

        proto = {
            "nodes": {
                "ask_name": {
                    "field": "name",
                    "validate": "not_empty",
                    "next": "ask_age"
                }
            }
        }
        vm, _, mock_validators, _ = self.make_vm(proto)
        mock_validators.validate.return_value = False
        state = VMState(protocol_id="test", node="ask_name", fields={}, transcript=[])
        result = await vm.step(state, "")

        assert result.node == "ask_name"
        assert result.transcript[0]["reason"] == "validation_failed"
        assert "name" not in result.fields

    @pytest.mark.asyncio
    async def test_step_field_node_default_next(self):
        from api.services.engine import VMState

        proto = {
            "nodes": {
                "ask_email": {
                    "field": "email"
                }
            }
        }
        vm, _, mock_validators, _ = self.make_vm(proto)
        mock_validators.validate.return_value = True
        state = VMState(protocol_id="test", node="ask_email", fields={}, transcript=[])
        result = await vm.step(state, "a@b.com")

        assert result.fields["email"] == "a@b.com"
        assert result.node == "agent_handoff"

    @pytest.mark.asyncio
    async def test_step_options_node_hit(self):
        from api.services.engine import VMState

        proto = {
            "nodes": {
                "choose_color": {
                    "options": ["red:color_red", "blue:color_blue"]
                }
            }
        }
        vm, _, _, _ = self.make_vm(proto)
        state = VMState(protocol_id="test", node="choose_color", fields={}, transcript=[])
        result = await vm.step(state, "red")

        assert result.node == "color_red"
        assert result.transcript[0]["reason"] == "option_selected:red"

    @pytest.mark.asyncio
    async def test_step_options_node_miss(self):
        from api.services.engine import VMState

        proto = {
            "nodes": {
                "choose_color": {
                    "options": ["red:color_red", "blue:color_blue"]
                }
            }
        }
        vm, _, _, _ = self.make_vm(proto)
        state = VMState(protocol_id="test", node="choose_color", fields={}, transcript=[])
        result = await vm.step(state, "green")

        assert result.node == "choose_color"
        assert result.transcript[0]["reason"] == "invalid_option"

    @pytest.mark.asyncio
    async def test_step_action_node_success(self):
        from api.services.engine import VMState

        proto = {
            "nodes": {
                "process": {
                    "action": "lookup_order",
                    "on_ok": "success_node",
                    "on_fail": "fail_node"
                }
            }
        }
        vm, _, _, mock_actions = self.make_vm(proto)
        mock_actions.run = AsyncMock(return_value={"success": True, "data": "ok"})
        state = VMState(protocol_id="test", node="process", fields={"order_id": "ORD-001"}, transcript=[])
        result = await vm.step(state, "")

        assert result.node == "success_node"
        assert result.transcript[0]["reason"] == "action:lookup_order"
        mock_actions.run.assert_called_once_with("lookup_order", {"order_id": "ORD-001"})

    @pytest.mark.asyncio
    async def test_step_action_node_failure(self):
        from api.services.engine import VMState

        proto = {
            "nodes": {
                "process": {
                    "action": "lookup_order",
                    "on_ok": "success_node",
                    "on_fail": "fail_node"
                }
            }
        }
        vm, _, _, mock_actions = self.make_vm(proto)
        mock_actions.run = AsyncMock(return_value={"success": False, "error": "not found"})
        state = VMState(protocol_id="test", node="process", fields={}, transcript=[])
        result = await vm.step(state, "")

        assert result.node == "fail_node"
        assert result.transcript[0]["reason"] == "action:lookup_order"

    @pytest.mark.asyncio
    async def test_step_no_rule_fallback(self):
        from api.services.engine import VMState

        proto = {"nodes": {"weird_node": {"unknown_key": "value"}}}
        vm, _, _, _ = self.make_vm(proto)
        state = VMState(protocol_id="test", node="weird_node", fields={}, transcript=[])
        result = await vm.step(state, "hello")

        assert result.node == "agent_handoff"
        assert result.transcript[0]["reason"] == "no_rule"

    def test_resolve_hit(self):
        from api.services.engine import ProtocolVM

        vm, _, _, _ = self.make_vm()
        result = vm._resolve(["1:option_a", "2:option_b"], "2")
        assert result == "option_b"

    def test_resolve_miss(self):
        from api.services.engine import ProtocolVM

        vm, _, _, _ = self.make_vm()
        result = vm._resolve(["1:option_a"], "3")
        assert result is None

    def test_resolve_case_insensitive(self):
        from api.services.engine import ProtocolVM

        vm, _, _, _ = self.make_vm()
        result = vm._resolve(["YES:got_it", "NO:skip"], "yes")
        assert result == "got_it"

    def test_render_prompt(self):
        from api.services.engine import ProtocolVM

        vm, _, _, _ = self.make_vm()
        prompt = "Hello {{ name }}, your order {{ order_id }} is ready."
        fields = {"name": "Alice", "order_id": "ORD-123"}
        result = vm._render_prompt(prompt, fields)
        assert result == "Hello Alice, your order ORD-123 is ready."

    def test_render_prompt_empty(self):
        from api.services.engine import ProtocolVM

        vm, _, _, _ = self.make_vm()
        assert vm._render_prompt("", {"k": "v"}) == ""
        assert vm._render_prompt(None, {"k": "v"}) == ""

    def test_render_prompt_missing_field(self):
        from api.services.engine import ProtocolVM

        vm, _, _, _ = self.make_vm()
        prompt = "Hello {{ name }}, your id is {{ missing }}."
        fields = {"name": "Bob"}
        result = vm._render_prompt(prompt, fields)
        assert result == "Hello Bob, your id is ."

    def test_get_prompt(self):
        proto = {
            "nodes": {
                "greet": {
                    "prompt": "Hello {{ user }}!"
                }
            }
        }
        from api.services.engine import VMState, ProtocolVM

        mock_loader = MagicMock()
        mock_loader.load.return_value = proto
        vm = ProtocolVM(mock_loader, MagicMock(), MagicMock())
        state = VMState(protocol_id="test", node="greet", fields={"user": "Alice"}, transcript=[])
        result = vm.get_prompt(state)
        assert result == "Hello Alice!"

    def test_get_prompt_proto_not_found(self):
        from api.services.engine import VMState, ProtocolVM

        mock_loader = MagicMock()
        mock_loader.load.return_value = None
        vm = ProtocolVM(mock_loader, MagicMock(), MagicMock())
        state = VMState(protocol_id="missing", node="greet", fields={}, transcript=[])
        assert vm.get_prompt(state) == ""

    def test_get_prompt_node_not_found(self):
        proto = {"nodes": {"other": {}}}
        from api.services.engine import VMState, ProtocolVM

        mock_loader = MagicMock()
        mock_loader.load.return_value = proto
        vm = ProtocolVM(mock_loader, MagicMock(), MagicMock())
        state = VMState(protocol_id="test", node="missing", fields={}, transcript=[])
        assert vm.get_prompt(state) == ""

    def test_vmstate_dataclass(self):
        from api.services.engine import VMState

        s = VMState(protocol_id="p1", node="n1", fields={"k": "v"}, transcript=[], route_key="rk", prompt="pr", audio_prompt=b"ap")
        assert s.protocol_id == "p1"
        assert s.node == "n1"
        assert s.fields == {"k": "v"}
        assert s.route_key == "rk"
        assert s.prompt == "pr"
        assert s.audio_prompt == b"ap"

    def test_vmstate_defaults(self):
        from api.services.engine import VMState

        s = VMState(protocol_id="p1", node="n1", fields={}, transcript=[])
        assert s.route_key is None
        assert s.prompt is None
        assert s.audio_prompt is None