import asyncio
from contextlib import asynccontextmanager

import httpx


class HTTPClientPool:
    """Connection pool for HTTP clients"""
    _instance = None
    _client: httpx.AsyncClient | None = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling"""
        if self._client is None or self._client.is_closed:
            async with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.AsyncClient(
                        limits=httpx.Limits(
                            max_keepalive_connections=20,
                            max_connections=100,
                            keepalive_expiry=30.0
                        ),
                        timeout=httpx.Timeout(60.0, connect=10.0),
                        follow_redirects=True
                    )
        return self._client

    async def close(self):
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

# Global instance
http_pool = HTTPClientPool()

@asynccontextmanager
async def get_http_client():
    """Context manager for getting HTTP client from pool"""
    client = await http_pool.get_client()
    try:
        yield client
    finally:
        # Don't close the client here - it's pooled
        pass
