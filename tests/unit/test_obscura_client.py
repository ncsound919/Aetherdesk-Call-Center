"""Unit tests for the Obscura CDP client."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from api.services.obscura_client import ObscuraClient, ObscuraError


class FakeWS:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []

    async def send(self, message: str):
        data = json.loads(message)
        self.sent.append(data)
        mid = data["id"]
        method = data["method"]
        if method == "Target.createTarget":
            result = {"targetId": "t1"}
        elif method == "Target.attachToTarget":
            result = {"sessionId": "s1"}
        elif method == "Runtime.evaluate":
            result = {"result": {"type": "string", "value": "hello"}}
        elif method == "LP.getMarkdown":
            result = {"markdown": "# Hi"}
        else:
            result = {}
        await self.queue.put(json.dumps({"id": mid, "result": result}))

    async def close(self):
        await self.queue.put(None)

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        while True:
            item = await self.queue.get()
            if item is None:
                break
            yield item


@pytest.mark.asyncio
async def test_new_page_and_evaluate_roundtrip():
    fake = FakeWS()
    with patch("api.services.obscura_client.websockets.connect", new=AsyncMock(return_value=fake)):
        client = ObscuraClient(url="ws://fake:9222", timeout=2)
        sid = await client.new_page()
        assert sid == "s1"
        await client.navigate("https://example.com")
        value = await client.evaluate("document.title")
        assert value == "hello"
        await client.close()


@pytest.mark.asyncio
async def test_page_markdown_extraction():
    fake = FakeWS()
    with patch("api.services.obscura_client.websockets.connect", new=AsyncMock(return_value=fake)):
        client = ObscuraClient(url="ws://fake:9222", timeout=2)
        md = await client.fetch_markdown("https://example.com")
        assert md == "# Hi"
        await client.close()


@pytest.mark.asyncio
async def test_command_timeout_raises():
    class SilentWS:
        def __init__(self):
            self.queue = asyncio.Queue()

        async def send(self, _message: str):
            pass

        async def close(self):
            pass

        def __aiter__(self):
            return self._iterate()

        async def _iterate(self):
            while True:
                item = await self.queue.get()
                if item is None:
                    break
                yield item

    silent = SilentWS()
    with patch(
        "api.services.obscura_client.websockets.connect", new=AsyncMock(return_value=silent)
    ):
        client = ObscuraClient(url="ws://fake:9222", timeout=0.05)
        with pytest.raises(ObscuraError):
            await client.evaluate("1+1")
        await client.close()
