"""Unit tests for the LLM client (DeepSeek primary + Ollama fallback)."""

from unittest.mock import AsyncMock, patch

import pytest

from api.services import llm_client as llm_mod
from api.services.llm_client import LLMClient, LlmClientError, parse_json_content


@pytest.fixture
def client():
    return LLMClient()


def test_parse_json_content_plain():
    assert parse_json_content('{"a": 1}') == {"a": 1}


def test_parse_json_content_markdown_fence():
    text = '```json\n{"hello": "world"}\n```'
    assert parse_json_content(text) == {"hello": "world"}


def test_parse_json_content_leading_prose():
    text = "Sure! Here is the result: {\"ok\": true} hope it helps"
    assert parse_json_content(text) == {"ok": True}


def test_parse_json_content_invalid_raises():
    with pytest.raises(ValueError):
        parse_json_content("not json at all")


def _http_response(status_code: int, body: dict, text: str | None = None):
    """Sync-response double: LLM client reads .status_code and .json() synchronously."""
    return AsyncMock(
        status_code=status_code,
        text=text if text is not None else str(body),
        json=lambda: body,
    )


@pytest.mark.asyncio
async def test_chat_returns_deepseek_result(client):
    mock_resp = _http_response(200, {
        "choices": [{"message": {"content": '{"route": "billing"}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    })
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.is_closed = False
    with patch.object(client, "_get_client", return_value=mock_client), \
         patch.object(llm_mod, "DEEPSEEK_API_KEY", "sk-test"):
        result = await client.chat([{"role": "user", "content": "hi"}], json_mode=True)
    assert result.provider == "deepseek"
    assert result.text == '{"route": "billing"}'
    assert result.model == "deepseek-v4-flash"
    mock_client.post.assert_called_once()
    call_body = mock_client.post.call_args.kwargs["json"]
    assert call_body["model"] == "deepseek-v4-flash"
    assert call_body["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_chat_falls_back_to_ollama_when_deepseek_fails(client):
    mock_ok = _http_response(200, {
        "message": {"content": "ollama answer"},
        "prompt_eval_count": 7,
    })
    mock_client = AsyncMock()
    mock_client.is_closed = False
    with patch.object(client, "_get_client", return_value=mock_client), \
         patch.object(llm_mod, "DEEPSEEK_API_KEY", "sk-test"), \
         patch.object(llm_mod, "LLM_FALLBACK_PROVIDER", "ollama"):
        # DeepSeek returns 500 first, Ollama succeeds second
        mock_client.post.side_effect = [
            _http_response(500, {}, text="err"),
            mock_ok,
        ]
        result = await client.chat([{"role": "user", "content": "hi"}])
    assert result.provider == "ollama"
    assert result.text == "ollama answer"


@pytest.mark.asyncio
async def test_chat_raises_when_all_providers_fail(client):
    mock_client = AsyncMock()
    mock_client.post.return_value = _http_response(503, {}, text="down")
    mock_client.is_closed = False
    with patch.object(client, "_get_client", return_value=mock_client), \
         patch.object(llm_mod, "DEEPSEEK_API_KEY", "sk-test"), \
         patch.object(llm_mod, "LLM_FALLBACK_PROVIDER", "ollama"):
        with pytest.raises(LlmClientError):
            await client.chat([{"role": "user", "content": "hi"}])
    # 2 attempts: deepseek + ollama
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_chat_retries_json_object_with_plain_prompt_on_empty(client):
    mock_empty = _http_response(200, {
        "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
    })
    mock_ok = _http_response(200, {
        "choices": [{"message": {"content": "{}"}}],
    })
    mock_client = AsyncMock()
    mock_client.post.side_effect = [mock_empty, mock_ok]
    mock_client.is_closed = False
    with patch.object(client, "_get_client", return_value=mock_client), \
         patch.object(llm_mod, "DEEPSEEK_API_KEY", "sk-test"):
        result = await client.chat([{"role": "user", "content": "hi"}], json_mode=True)
    assert result.text == "{}"
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_chat_returns_none_when_deepseek_key_missing(client):
    mock_client = AsyncMock()
    mock_client.post.return_value = _http_response(200, {"message": {"content": "x"}})
    mock_client.is_closed = False
    with patch.object(client, "_get_client", return_value=mock_client), \
         patch.object(llm_mod, "DEEPSEEK_API_KEY", ""), \
         patch.object(llm_mod, "LLM_FALLBACK_PROVIDER", "ollama"):
        result = await client.chat([{"role": "user", "content": "hi"}])
    # Only Ollama is tried (deepseek skipped due to missing key)
    assert result.provider == "ollama"
