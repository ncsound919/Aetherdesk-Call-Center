"""Unified LLM client for Aetherdesk.

Primary provider: DeepSeek V4 Flash (OpenAI-compatible chat.completions).
Fallback provider: local Ollama (OpenAI-incompatible /api/chat).

This is the single point of truth for all LLM calls. Every agent path
(voice, SMS, chat, intent classification, script generation) should route
through `chat()` so that:

  * provider selection / failover is centralized
  * JSON mode handles DeepSeek's documented json_object flakiness
    (empty content) with a plain-JSON fallback, mirroring the proven
    strategy used by the Overlay Justice client
  * per-call provider + token usage is returned for campaign budget
    tracking (see `LlmResult.provider`, `usage`)
"""

import asyncio
import json
import os
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

# --- Provider configuration -------------------------------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "qwen3:1.7b")
LLM_FALLBACK_PROVIDER = os.getenv("LLM_FALLBACK_PROVIDER", "ollama")

# LiteLLM AI gateway (OpenAI-compatible). When configured it becomes the
# preferred provider: multi-provider failover, cost tracking, guardrails.
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "")
LITELLM_MODEL = os.getenv("LITELLM_MODEL", "deepseek-main")

LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))


class LlmResult:
    """Normalized result of an LLM call."""

    __slots__ = ("text", "provider", "model", "usage", "latency_ms")

    def __init__(
        self,
        text: str,
        provider: str,
        model: str,
        usage: dict[str, int] | None = None,
        latency_ms: float = 0.0,
    ):
        self.text = text
        self.provider = provider
        self.model = model
        self.usage = usage or {}
        self.latency_ms = latency_ms

    def estimated_cost_usd(self) -> float:
        """Rough per-call cost for budget tracking (DeepSeek pricing only;
        local Ollama is treated as $0)."""
        if self.provider != "deepseek":
            return 0.0
        in_tokens = int(self.usage.get("prompt_tokens", 0) or 0)
        out_tokens = int(self.usage.get("completion_tokens", 0) or 0)
        # DeepSeek V4 Flash: approximate $0.14 / 1M input, $0.42 / 1M output.
        return (in_tokens * 0.14 + out_tokens * 0.42) / 1_000_000


class LlmClientError(Exception):
    """Raised when all providers fail."""

    def __init__(self, message: str, last_error: str = ""):
        super().__init__(message)
        self.last_error = last_error


class LLMClient:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=LLM_TIMEOUT,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # --- DeepSeek (primary) -------------------------------------------------

    async def _deepseek_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        json_mode: bool,
        model: str,
    ) -> dict[str, Any] | None:
        """Call DeepSeek chat.completions. Returns parsed JSON body or None.

        json_object mode can return empty content intermittently; when that
        happens we retry once with a plain-JSON prompt (no response_format)
        that describes the desired shape in words — never echoing the raw
        schema, which the model tends to copy back into its output.
        """
        if not DEEPSEEK_API_KEY:
            return None

        client = self._get_client()
        base_body: dict[str, Any] = {
            "model": model,
            "stream": False,
            "temperature": temperature,
        }

        attempts: list[tuple[dict[str, Any], str]] = []
        if json_mode:
            shape_prompt = (
                "\n\nRespond with a single valid JSON object. "
                "Return ONLY the JSON data — no markdown fences, no explanation, "
                "no preamble, no schema echo."
            )
            messages_json = [
                {"role": m["role"], "content": m["content"] + shape_prompt}
                if m["role"] == "user"
                else m
                for m in messages
            ]
            attempts.append(
                (
                    {
                        **base_body,
                        "messages": messages_json,
                        "response_format": {"type": "json_object"},
                    },
                    "json_object",
                )
            )
            attempts.append(
                (
                    {**base_body, "messages": messages},
                    "plain-json",
                )
            )
        else:
            attempts.append((base_body, "default"))

        last_error = ""
        for body, label in attempts:
            try:
                resp = await client.post(
                    f"{DEEPSEEK_BASE_URL}/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    },
                    json=body,
                )
                if resp.status_code != 200:
                    last_error = f"DeepSeek HTTP {resp.status_code}: {resp.text[:200]}"
                    logger.warning(
                        "deepseek_http_error", label=label, status=resp.status_code
                    )
                    continue
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                content = (choice.get("message") or {}).get("content") or ""
                if not content.strip():
                    finish = choice.get("finish_reason", "unknown")
                    last_error = f"DeepSeek empty content (finish_reason={finish})"
                    logger.warning(
                        "deepseek_empty_content", label=label, finish_reason=finish
                    )
                    continue
                return {
                    "content": content,
                    "usage": data.get("usage") or {},
                    "model": model,
                }
            except (TimeoutError, httpx.HTTPError) as e:
                last_error = str(e)
                logger.warning("deepseek_request_error", label=label, error=last_error)

        logger.warning("deepseek_all_attempts_failed", error=last_error)
        return None

    # --- Local Ollama (fallback) --------------------------------------------

    async def _ollama_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        json_mode: bool,
        model: str,
    ) -> dict[str, Any] | None:
        """Call local Ollama /api/chat (Ollama-native shape, not OpenAI)."""
        client = self._get_client()
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if json_mode:
            body["format"] = "json"

        try:
            resp = await client.post(f"{OLLAMA_HOST}/api/chat", json=body)
            if resp.status_code != 200:
                logger.warning("ollama_http_error", status=resp.status_code)
                return None
            data = resp.json()
            content = (data.get("message") or {}).get("content") or ""
            if not content.strip():
                return None
            usage = data.get("prompt_eval_count", 0)
            return {
                "content": content,
                "usage": {"prompt_tokens": usage or 0, "completion_tokens": 0},
                "model": model,
            }
        except (TimeoutError, httpx.HTTPError) as e:
            logger.warning("ollama_request_error", error=str(e))
            return None

    # --- LiteLLM gateway (preferred when configured) ------------------------

    async def _gateway_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        json_mode: bool,
        model: str,
    ) -> dict[str, Any] | None:
        """Call the LiteLLM proxy (OpenAI-format /chat/completions)."""
        if not LITELLM_BASE_URL:
            return None

        client = self._get_client()
        body: dict[str, Any] = {
            "model": model,
            "stream": False,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        try:
            headers = {"Content-Type": "application/json"}
            if LITELLM_API_KEY:
                headers["Authorization"] = f"Bearer {LITELLM_API_KEY}"
            resp = await client.post(
                f"{LITELLM_BASE_URL}/chat/completions",
                headers=headers,
                json=body,
            )
            if resp.status_code != 200:
                logger.warning(
                    "litellm_http_error",
                    status=resp.status_code,
                    detail=resp.text[:200],
                )
                return None
            data = resp.json()
            choice = (data.get("choices") or [{}])[0]
            content = (choice.get("message") or {}).get("content") or ""
            if not content.strip():
                return None
            return {
                "content": content,
                "usage": data.get("usage") or {},
                "model": model,
            }
        except (TimeoutError, httpx.HTTPError) as e:
            logger.warning("litellm_request_error", error=str(e))
            return None

    # --- Public API ----------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        json_mode: bool = False,
        model: str | None = None,
        force_provider: str | None = None,
    ) -> LlmResult:
        """Primary entry point for all LLM calls.

        provider order: deepseek -> ollama (fallback) unless force_provider.
        Returns the first non-None result; raises LlmClientError if all fail.
        """
        start = asyncio.get_event_loop().time()

        preferred = force_provider or "deepseek"
        if preferred == "deepseek":
            candidates: list[tuple[str, str]] = [
                ("litellm", model or LITELLM_MODEL),
                ("deepseek", model or DEEPSEEK_MODEL),
                (LLM_FALLBACK_PROVIDER, model or LLM_FALLBACK_MODEL),
            ]
        else:
            candidates = [(LLM_FALLBACK_PROVIDER, model or LLM_FALLBACK_MODEL)]

        last_error = ""
        for provider, model_name in candidates:
            if provider == "litellm":
                result = await self._gateway_chat(
                    messages, temperature, json_mode, model_name
                )
            elif provider == "deepseek":
                result = await self._deepseek_chat(
                    messages, temperature, json_mode, model_name
                )
            elif provider == "ollama":
                result = await self._ollama_chat(
                    messages, temperature, json_mode, model_name
                )
            else:
                continue

            if result:
                latency_ms = (asyncio.get_event_loop().time() - start) * 1000
                return LlmResult(
                    text=result["content"],
                    provider=provider,
                    model=result["model"],
                    usage=result.get("usage"),
                    latency_ms=latency_ms,
                )
            last_error = f"{provider} unavailable"

        raise LlmClientError("All LLM providers failed", last_error)


llm_client = LLMClient()


def parse_json_content(text: str) -> dict[str, Any]:
    """Parse JSON content tolerating markdown fences and leading prose.

    Returns the first JSON object found; raises ValueError if none.
    """
    text = text.strip()
    # Strip markdown fences if present.
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fall back to extracting the first {...} block.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM output: {text[:200]}")
