import asyncio
import httpx
from loguru import logger

GAMMA_API_BASE = "https://gamma-api.polymarket.com"


class PolymarketClient:
    """Public Gamma API client for market discovery."""

    def __init__(self, base_url: str = GAMMA_API_BASE):
        self.base_url = base_url
        self._last_call = 0.0
        self._min_interval = 0.60
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=10),
        )

    async def _rate_limit(self):
        now = asyncio.get_event_loop().time()
        wait = self._last_call + self._min_interval - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = asyncio.get_event_loop().time()

    async def close(self):
        await self._client.aclose()

    async def list_events(self, active: bool = True, limit: int = 100, tag_id: int | None = None) -> list[dict]:
        params: dict = {
            "active": str(active).lower(),
            "closed": "false",
            "limit": limit,
            "order": "volume_24hr",
            "ascending": "false",
        }
        if tag_id:
            params["tag_id"] = tag_id
        await self._rate_limit()
        resp = await self._client.get("/events", params=params)
        resp.raise_for_status()
        return resp.json()

    async def list_markets(self, limit: int = 100, volume_num_min: float | None = None) -> list[dict]:
        params: dict = {
            "limit": limit,
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
        }
        if volume_num_min:
            params["volume_num_min"] = volume_num_min
        await self._rate_limit()
        resp = await self._client.get("/markets", params=params)
        resp.raise_for_status()
        return resp.json()

    async def search(self, query: str) -> dict:
        await self._rate_limit()
        resp = await self._client.get("/search", params={"query": query})
        resp.raise_for_status()
        return resp.json()

    async def get_market_prices(self, token_ids: list[str]) -> list[dict]:
        """Get order book prices for a batch of tokens."""
        results = []
        for tid in token_ids:
            await self._rate_limit()
            try:
                book_resp = await self._client.get("/order-book", params={"token_id": tid})
                book_resp.raise_for_status()
                book = book_resp.json()
                bids = book.get("bids", [])
                asks = book.get("asks", [])
                best_bid = float(bids[0]["price"]) if bids else 0.0
                best_ask = float(asks[0]["price"]) if asks else 0.0
                midpoint = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.5
                results.append({
                    "token_id": tid,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "midpoint": midpoint,
                })
            except Exception as e:
                logger.warning(f"Failed to fetch price for token {tid}: {e}")
                results.append({"token_id": tid, "best_bid": 0.0, "best_ask": 0.0, "midpoint": 0.5})
        return results
