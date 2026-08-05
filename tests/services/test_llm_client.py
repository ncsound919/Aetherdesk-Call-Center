import asyncio
import json

import httpx
import pytest

from api.services.llm_client import (
    LLMClient,
    LlmClientError,
    LlmResult,
    llm_client,
    parse_json_content,
)


@pytest.fixture
def mock_transport():
    """Build an httpx AsyncClient backed by a MockTransport dispatcher."""

    def build(handler):
        client = LLMClient()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return client

    return build


def test_parse_json_content_plain():
    assert parse_json_content('{"a": 1}') == {"a": 1}


def test_parse_json_content_fenced():
    assert parse_json_content('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_content_embedded():
    assert parse_json_content('Here is the data:\n{"a": 1}\nThat is all.') == {"a": 1}


def test_parse_json_content_invalid_raises():
    with pytest.raises(ValueError):
        parse_json_content("not json at all")


@pytest.mark.asyncio
async def test_deepseek_primary_success(mock_transport, monkeypatch):
    monkeypatch.setattr("api.services.llm_client.DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("api.services.llm_client.DEEPSEEK_MODEL", "deepseek-v4-flash")

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "deepseek-v4-flash"
        assert "Authorization" in request.headers
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"response": "hello"}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    client = mock_transport(handler)
    res = await client.chat(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}],
        json_mode=True,
    )
    assert isinstance(res, LlmResult)
    assert res.provider == "deepseek"
    assert res.text == '{"response": "hello"}'
    assert res.usage["prompt_tokens"] == 10
    assert res.estimated_cost_usd() > 0


@pytest.mark.asyncio
async def test_deepseek_empty_then_plain_fallback(mock_transport):
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
                "usage": {},
            },
        )

    client = mock_transport(handler)
    # All attempts return empty -> deepseek fails -> falls through to ollama
    # which is unreachable -> LlmClientError.
    with pytest.raises(LlmClientError):
        await client.chat([{"role": "user", "content": "hi"}], json_mode=True)


@pytest.mark.asyncio
async def test_ollama_fallback_on_deepseek_failure(mock_transport):
    async def handler(request: httpx.Request) -> httpx.Response:
        if "deepseek.com" in str(request.url):
            return httpx.Response(500, json={})
        # Ollama /api/chat
        return httpx.Response(
            200,
            json={"message": {"content": '{"response": "local reply"}'}, "prompt_eval_count": 3},
        )

    client = mock_transport(handler)
    res = await client.chat([{"role": "user", "content": "hi"}], json_mode=True)
    assert res.provider == "ollama"
    assert res.text == '{"response": "local reply"}'
    assert res.estimated_cost_usd() == 0.0


@pytest.mark.asyncio
async def test_all_providers_fail_raises(mock_transport):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    client = mock_transport(handler)
    with pytest.raises(LlmClientError):
        await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_force_provider_ollama(mock_transport):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"content": "plain reply"}, "prompt_eval_count": 1},
        )

    client = mock_transport(handler)
    res = await client.chat(
        [{"role": "user", "content": "hi"}],
        force_provider="ollama",
        json_mode=False,
    )
    assert res.provider == "ollama"
