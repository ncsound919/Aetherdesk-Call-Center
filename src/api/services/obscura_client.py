"""Minimal async CDP client for the Obscura headless browser.

Connects to Obscura's CDP WebSocket (default ws://localhost:9222/devtools/browser)
and exposes page navigation, JavaScript evaluation, and DOM-to-markdown
extraction for AI-agent browsing and web scraping.
"""

import asyncio
import json
import os
import uuid

import structlog
import websockets

logger = structlog.get_logger()

OBSCURA_CDP_URL = os.getenv("OBSCURA_CDP_URL", "ws://localhost:9222/devtools/browser")
OBSCURA_TIMEOUT = float(os.getenv("OBSCURA_TIMEOUT", "30"))


class ObscuraError(Exception):
    """Raised when a CDP command fails or times out."""


class ObscuraClient:
    def __init__(self, url: str | None = None, timeout: float = OBSCURA_TIMEOUT):
        self._url = url or OBSCURA_CDP_URL
        self._timeout = timeout
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._session_id: str | None = None
        self._target_id: str | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._reader: asyncio.Task | None = None

    async def _connect(self):
        self._ws = await websockets.connect(self._url, max_size=64 * 1024 * 1024)
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self):
        try:
            async for raw in self._ws:
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                mid = data.get("id")
                if mid in self._pending:
                    fut = self._pending.pop(mid)
                    if not fut.done():
                        if "error" in data:
                            fut.set_exception(ObscuraError(str(data["error"])))
                        else:
                            fut.set_result(data.get("result") or {})
        except Exception as e:
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(ObscuraError(str(e)))
            self._pending.clear()

    async def _send(self, method: str, params: dict | None = None) -> dict:
        if self._ws is None:
            await self._connect()
        mid = uuid.uuid4().int & 0xFFFFFFFFFFFFFFFF
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        msg: dict = {"id": mid, "method": method}
        if params:
            msg["params"] = params
        if self._session_id:
            msg["sessionId"] = self._session_id
        await self._ws.send(json.dumps(msg))
        try:
            return await asyncio.wait_for(fut, timeout=self._timeout)
        except TimeoutError:
            self._pending.pop(mid, None)
            raise ObscuraError(f"CDP command timed out: {method}") from None

    async def new_page(self, url: str = "about:blank") -> str:
        res = await self._send("Target.createTarget", {"url": url})
        self._target_id = res["targetId"]
        att = await self._send(
            "Target.attachToTarget", {"targetId": self._target_id, "flatten": True}
        )
        self._session_id = att["sessionId"]
        return self._session_id

    async def navigate(self, url: str) -> None:
        if self._session_id is None:
            await self.new_page()
        await self._send("Page.navigate", {"url": url})

    async def evaluate(self, expression: str):
        res = await self._send(
            "Runtime.evaluate", {"expression": expression, "returnByValue": True}
        )
        return (res.get("result") or {}).get("value")

    async def page_markdown(self) -> str:
        res = await self._send("LP.getMarkdown", {})
        if isinstance(res, dict) and "markdown" in res:
            return res["markdown"]
        if isinstance(res, dict) and "result" in res:
            inner = res["result"]
            if isinstance(inner, dict) and "value" in inner:
                return str(inner["value"])
        return json.dumps(res)

    async def fetch_markdown(self, url: str) -> str:
        await self.navigate(url)
        return await self.page_markdown()

    async def close(self):
        if self._reader:
            self._reader.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._session_id = None
        self._target_id = None
