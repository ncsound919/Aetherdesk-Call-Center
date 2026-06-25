import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.intent_classifier import IntentClassifier, IntentResult


class TestIntentClassifierInit:
    def test_default_model_and_host(self):
        with patch.dict("os.environ", {}, clear=True):
            cls = IntentClassifier()
            assert cls.model == "llama3.2:1b"
            assert cls.host == "http://localhost:11434"

    def test_custom_model_and_host(self):
        cls = IntentClassifier(model="custom:latest", host="http://custom:8080")
        assert cls.model == "custom:latest"
        assert cls.host == "http://custom:8080"

    def test_env_vars(self):
        with patch("api.services.intent_classifier.OLLAMA_MODEL", "mistral:7b"), \
             patch("api.services.intent_classifier.OLLAMA_HOST", "http://ollama:11434"):
            cls = IntentClassifier()
            assert cls.model == "mistral:7b"
            assert cls.host == "http://ollama:11434"


class TestIntentClassifierKeywordFallback:
    @pytest.mark.asyncio
    async def test_refund_keyword(self):
        cls = IntentClassifier()
        result = await cls._keyword_fallback("I want a refund please")
        assert result.intent == "billing_refund"
        assert result.confidence == 0.5
        assert "refund" in result.reasoning

    @pytest.mark.asyncio
    async def test_agent_keyword(self):
        cls = IntentClassifier()
        result = await cls._keyword_fallback("talk to an agent")
        assert result.intent == "agent_handoff"
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_prescription_keyword(self):
        cls = IntentClassifier()
        result = await cls._keyword_fallback("need a prescription refill")
        assert result.intent == "pharmacy_refill"

    @pytest.mark.asyncio
    async def test_no_match_returns_general(self):
        cls = IntentClassifier()
        result = await cls._keyword_fallback("what is the weather today")
        assert result.intent == "generalInquiry"
        assert result.confidence == 0.2

    @pytest.mark.asyncio
    async def test_case_insensitive(self):
        cls = IntentClassifier()
        result = await cls._keyword_fallback("AGENT please")
        assert result.intent == "agent_handoff"

    @pytest.mark.asyncio
    async def test_multiple_keywords_first_wins(self):
        cls = IntentClassifier()
        result = await cls._keyword_fallback("I need a refund for my prescription")
        assert result.intent == "billing_refund"


class TestIntentClassifierClassify:
    @pytest.mark.asyncio
    async def test_empty_transcript(self):
        cls = IntentClassifier()
        result = await cls.classify("")
        assert result.intent == "generalInquiry"
        assert result.confidence == 0.0
        assert "Empty transcript" in result.reasoning

    @pytest.mark.asyncio
    async def test_whitespace_transcript(self):
        cls = IntentClassifier()
        result = await cls.classify("   ")
        assert result.intent == "generalInquiry"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_successful_ollama_response(self):
        cls = IntentClassifier()
        ollama_response = {
            "message": {
                "content": '{"intent": "pharmacy_refill", "entities": {"rx_number": "12345"}, "confidence": 0.95, "reasoning": "Patient wants refill"}'
            }
        }
        with patch.object(cls, "_call_ollama", AsyncMock(return_value=ollama_response)), \
             patch("api.services.intent_classifier.track_llm_latency") as mock_track:
            result = await cls.classify("I need to refill RX 12345")

        assert result.intent == "pharmacy_refill"
        assert result.entities == {"rx_number": "12345"}
        assert result.confidence == 0.95
        mock_track.assert_called_once()

    @pytest.mark.asyncio
    async def test_ollama_returns_no_intent_falls_back(self):
        cls = IntentClassifier()
        ollama_response = {
            "message": {
                "content": '{"entities": {}, "confidence": 0.1}'
            }
        }
        with patch.object(cls, "_call_ollama", AsyncMock(return_value=ollama_response)):
            result = await cls.classify("help me with refund")

        assert result.intent == "billing_refund"
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_ollama_returns_invalid_json(self):
        cls = IntentClassifier()
        ollama_response = {
            "message": {
                "content": "not valid json"
            }
        }
        with patch.object(cls, "_call_ollama", AsyncMock(return_value=ollama_response)):
            result = await cls.classify("I need help")

        assert result.intent == "generalInquiry"
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_ollama_returns_empty_content(self):
        cls = IntentClassifier()
        ollama_response = {"message": {"content": ""}}
        with patch.object(cls, "_call_ollama", AsyncMock(return_value=ollama_response)):
            result = await cls.classify("test")
        assert result.intent == "generalInquiry"

    @pytest.mark.asyncio
    async def test_ollama_raises_exception(self):
        cls = IntentClassifier()
        with patch.object(cls, "_call_ollama", AsyncMock(side_effect=Exception("Connection refused"))):
            result = await cls.classify("I want an agent")

        assert result.intent == "agent_handoff"
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_classify_missing_message_key(self):
        cls = IntentClassifier()
        with patch.object(cls, "_call_ollama", AsyncMock(return_value={})):
            result = await cls.classify("help")
        assert result.intent == "generalInquiry"


class TestIntentClassifierCallOllama:
    @pytest.mark.asyncio
    async def test_call_ollama_success(self):
        cls = IntentClassifier()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": '{"intent":"test"}'}}
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("api.services.intent_classifier.get_http_client") as mock_get_client:
            mock_get_client.return_value.__aenter__.return_value = mock_client
            result = await cls._call_ollama("test transcript")

        assert result["message"]["content"] == '{"intent":"test"}'
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_ollama_with_session_memory(self):
        cls = IntentClassifier()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": '{}'}}
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("api.services.intent_classifier.get_http_client") as mock_get_client, \
             patch("api.services.intent_classifier.memory_service") as mock_memory:
            mock_get_client.return_value.__aenter__.return_value = mock_client
            mock_memory.search_memories = AsyncMock(return_value=[
                {"content": "Customer mentioned order ORD-001"},
                {"content": "Customer is frustrated"}
            ])
            result = await cls._call_ollama("where is my order", session_id="SESS-001")

        assert result is not None
        mock_memory.search_memories.assert_called_once_with(
            query="where is my order", session_id="SESS-001", k=3
        )

    @pytest.mark.asyncio
    async def test_call_ollama_memory_search_fails_gracefully(self):
        cls = IntentClassifier()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": '{}'}}
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("api.services.intent_classifier.get_http_client") as mock_get_client, \
             patch("api.services.intent_classifier.memory_service") as mock_memory:
            mock_get_client.return_value.__aenter__.return_value = mock_client
            mock_memory.search_memories = AsyncMock(side_effect=Exception("Memory error"))
            result = await cls._call_ollama("test", session_id="SESS-001")

        assert result is not None
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_ollama_http_error(self):
        cls = IntentClassifier()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=Exception("HTTP 500"))

        with patch("api.services.intent_classifier.get_http_client") as mock_get_client, \
             pytest.raises(Exception, match="HTTP 500"):
            mock_get_client.return_value.__aenter__.return_value = mock_client
            await cls._call_ollama("test")

        mock_client.post.assert_called_once()


class TestIntentClassifierClassifyWithRetry:
    @pytest.mark.asyncio
    async def test_succeeds_first_attempt(self):
        cls = IntentClassifier()
        expected = IntentResult(intent="pharmacy_refill", entities={}, confidence=0.9, reasoning="ok")
        with patch.object(cls, "classify", AsyncMock(return_value=expected)):
            result = await cls.classify_with_retry("refill please")
        assert result.intent == "pharmacy_refill"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_retries_and_eventually_succeeds(self):
        cls = IntentClassifier()
        expected = IntentResult(intent="order_status", entities={}, confidence=0.8, reasoning="ok")
        call_count = 0

        async def mock_classify(transcript):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("temporary error")
            return expected

        with patch.object(cls, "classify", mock_classify):
            result = await cls.classify_with_retry("order status", max_retries=3)
        assert result.intent == "order_status"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_all_retries_fail(self):
        cls = IntentClassifier()
        with patch.object(cls, "classify", AsyncMock(side_effect=Exception("persistent error"))):
            result = await cls.classify_with_retry("test", max_retries=2)
        assert result.intent == "agent_handoff"
        assert result.confidence == 0.0
        assert "Failed after 2 attempts" in result.reasoning


class TestIntentClassifierClassifyWithFallback:
    @pytest.mark.asyncio
    async def test_high_confidence_returns_as_is(self):
        cls = IntentClassifier()
        with patch.object(cls, "classify", AsyncMock(return_value=IntentResult(
            intent="order_status", entities={"order_id": "ORD-001"}, confidence=0.8, reasoning="clear"
        ))):
            result = await cls.classify_with_fallback("where is my order")

        assert result.intent == "order_status"
        assert result.entities == {"order_id": "ORD-001"}
        assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_low_confidence_defaults_to_fallback(self):
        cls = IntentClassifier()
        with patch.object(cls, "classify", AsyncMock(return_value=IntentResult(
            intent="pharmacy_refill", entities={"rx": "123"}, confidence=0.3, reasoning="unclear"
        ))):
            result = await cls.classify_with_fallback("some unclear text")

        assert result.intent == "generalInquiry"
        assert result.entities == {"rx": "123"}
        assert result.confidence == 0.5
        assert "Low confidence" in result.reasoning

    @pytest.mark.asyncio
    async def test_low_confidence_custom_fallback(self):
        cls = IntentClassifier()
        with patch.object(cls, "classify", AsyncMock(return_value=IntentResult(
            intent="pharmacy_refill", entities={}, confidence=0.1, reasoning="low"
        ))):
            result = await cls.classify_with_fallback("test", fallback_intent="agent_handoff")

        assert result.intent == "agent_handoff"


class TestIntentResult:
    def test_intent_result_dataclass(self):
        result = IntentResult(intent="test", entities={"k": "v"}, confidence=0.5, reasoning="reason")
        assert result.intent == "test"
        assert result.entities == {"k": "v"}
        assert result.confidence == 0.5
        assert result.reasoning == "reason"
