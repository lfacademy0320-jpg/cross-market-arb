import time
import asyncio
import httpx
from loguru import logger

KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiClient:
    """Public Kalshi REST API client — read-only market data."""

    def __init__(self, base_url: str = KALSHI_API_BASE):
        self.base_url = base_url
        self._last_call = 0.0
        self._min_interval = 0.30
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=10),
        )

    async def _rate_limit(self):
        now = time.monotonic()
        wait = self._last_call + self._min_interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = time.monotonic()

    async def close(self):
        await self._client.aclose()

    async def list_events(self, status: str = "open", limit: int = 100) -> list[dict]:
        await self._rate_limit()
        resp = await self._client.get("/events", params={"status": status, "limit": limit})
        resp.raise_for_status()
        data = resp.json()
        return data.get("events", [])

    async def get_event(self, event_ticker: str) -> dict:
        await self._rate_limit()
        resp = await self._client.get(f"/events/{event_ticker}")
        resp.raise_for_status()
        return resp.json()

    async def list_markets(self, event_ticker: str = "", status: str = "open", limit: int = 100) -> list[dict]:
        await self._rate_limit()
        params: dict = {"status": status, "limit": limit}
        if event_ticker:
            params["event_ticker"] = event_ticker
        resp = await self._client.get("/markets", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("markets", [])

    async def get_market(self, ticker: str) -> dict:
        await self._rate_limit()
        resp = await self._client.get(f"/markets/{ticker}")
        resp.raise_for_status()
        data = resp.json()
        return data.get("market", {})

    async def get_market_order_book(self, ticker: str) -> dict:
        await self._rate_limit()
        resp = await self._client.get(f"/markets/{ticker}/orderbook")
        resp.raise_for_status()
        data = resp.json()
        return data.get("order_book", {})

    async def get_batch_quotes(self, tickers: list[str]) -> dict:
        """Batch fetch ticker quotes for price comparison."""
        await self._rate_limit()
        resp = await self._client.post("/batch/quotes", json={"tickers": tickers})
        resp.raise_for_status()
        data = resp.json()
        return data.get("quotes", {})

    async def get_settlement_history(self, ticker: str, limit: int = 5) -> list[dict]:
        """Fetch settlement history for a market to detect rule divergence patterns."""
        await self._rate_limit()
        try:
            resp = await self._client.get(f"/markets/{ticker}/settlements", params={"limit": limit})
            resp.raise_for_status()
            return resp.json().get("settlements", [])
        except Exception:
            return []
