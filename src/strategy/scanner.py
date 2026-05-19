"""Main cross-platform arbitrage scanner orchestration."""
import json
import time
from loguru import logger

from ..config import ScanSettings, SpreadOpportunity
from ..data.polymarket import PolymarketClient
from ..data.kalshi import KalshiClient
from ..data.comparator import match_events, calculate_spread
from ..strategy.settlement_check import check_settlement_risk


def _parse_pm_price(market: dict) -> float | None:
    """Extract Polymarket YES price from market data.

    Tries outcomePrices (Gamma API), then falls back to order book fetch.
    Returns None if no price is available.
    """
    raw_prices = market.get("outcomePrices")
    if raw_prices:
        try:
            prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
            yes_str = prices[0] if isinstance(prices, list) else prices.get("yes", "0.5")
            price = float(yes_str)
            if 0 < price < 1:
                return price
        except (json.JSONDecodeError, ValueError, IndexError, TypeError):
            pass

    clob_ids = market.get("clobTokenIds")
    if clob_ids:
        try:
            ids = json.loads(clob_ids) if isinstance(clob_ids, str) else clob_ids
            if ids and isinstance(ids, list) and len(ids) > 0:
                return None
        except (json.JSONDecodeError, TypeError):
            pass

    return None


def _parse_km_price(market: dict) -> float | None:
    """Extract Kalshi YES price from available fields.

    list_markets() provides last_price_dollars (most recent trade).
    get_market()/orderbook provide yes_bid/yes_ask for midpoint.
    """
    # Try order book fields first (from single-market or batch/quotes fetch)
    yes_bid = market.get("yes_bid")
    yes_ask = market.get("yes_ask")
    bid = float(yes_bid) if yes_bid is not None else None
    ask = float(yes_ask) if yes_ask is not None else None
    if bid is not None and ask is not None and 0 < bid < 1 and 0 < ask < 1:
        return round((bid + ask) / 2, 4)
    if bid is not None and 0 < bid < 1:
        return bid

    # Fall back to last_price_dollars (available in list_markets response)
    lpd = market.get("last_price_dollars")
    if lpd is not None:
        try:
            price = float(lpd)
            if 0 < price < 1:
                return price
        except (ValueError, TypeError):
            pass
    return None


class CrossPlatformScanner:
    """Orchestrates Polymarket-Kalshi cross-platform arbitrage scanning."""

    def __init__(self, settings: ScanSettings):
        self.settings = settings
        self.polymarket = PolymarketClient(settings.polymarket_gamma_url)
        self.kalshi = KalshiClient(settings.kalshi_api_url)

    async def close(self):
        await self.polymarket.close()
        await self.kalshi.close()

    async def scan(self, match_threshold: float = 0.55) -> list[SpreadOpportunity]:
        import asyncio as aio

        pm_markets = await self.polymarket.list_markets(
            limit=self.settings.max_scan_markets,
            volume_num_min=self.settings.min_volume_24h,
        )
        logger.info(f"Polymarket: {len(pm_markets)} markets loaded")

        # Kalshi: get events first, then fetch per-event markets (simple binary, not multivariate)
        # Cap at 40 events to keep total API calls manageable
        km_events = await self.kalshi.list_events(limit=min(self.settings.max_scan_markets, 40))
        logger.info(f"Kalshi: {len(km_events)} events loaded")

        # Fetch markets for all events in parallel batches of 10
        all_km_markets: list[dict] = []
        sem = aio.Semaphore(10)
        async def fetch_event_markets(event: dict) -> list[dict]:
            et = event.get("event_ticker") or event.get("ticker")
            if not et:
                return []
            async with sem:
                try:
                    markets = await self.kalshi.list_markets(event_ticker=et, limit=20)
                    for m in markets:
                        m["_event_title"] = event.get("title", "")
                    return markets
                except Exception:
                    return []

        tasks = [fetch_event_markets(e) for e in km_events]
        results = await aio.gather(*tasks)
        for r in results:
            all_km_markets.extend(r)
        logger.info(f"Kalshi: {len(all_km_markets)} per-event markets loaded")

        # Fetch order book prices for Polymarket markets that lack outcomePrices
        needs_order_book = [
            m for m in pm_markets if _parse_pm_price(m) is None
        ]
        if needs_order_book:
            token_ids = []
            for m in needs_order_book:
                raw = m.get("clobTokenIds", "")
                try:
                    ids = json.loads(raw) if isinstance(raw, str) else raw
                    if ids and isinstance(ids, list) and len(ids) > 0:
                        token_ids.append(ids[0])
                except (json.JSONDecodeError, TypeError):
                    pass
            if token_ids:
                ob_prices = await self.polymarket.get_market_prices(token_ids)
                for m, ob in zip(needs_order_book, ob_prices):
                    m["_ob_midpoint"] = ob.get("midpoint", 0.5)

        pairs = match_events(pm_markets, all_km_markets, threshold=match_threshold)

        opportunities: list[SpreadOpportunity] = []
        for pm, km, score in pairs:
            pm_price = _parse_pm_price(pm)
            if pm_price is None:
                pm_price = pm.get("_ob_midpoint", 0.5) or 0.5

            km_price = _parse_km_price(km)
            if km_price is None:
                continue

            spread = calculate_spread(pm_price, km_price)
            if not spread["actionable"] or spread["spread_pct"] < self.settings.min_profit_percent:
                continue

            risk = check_settlement_risk(
                pm.get("question", ""),
                pm.get("title", ""),
            )

            km_title = km.get("title", km.get("_event_title", ""))
            opp = SpreadOpportunity(
                event_title=km.get("_event_title", "") or pm.get("title", ""),
                market_title=pm.get("question", km_title),
                polymarket_price=round(pm_price, 4),
                kalshi_price=round(km_price, 4),
                spread_pct=spread["spread_pct"],
                polymarket_volume_24h=pm.get("volume24hr", 0) or pm.get("volume_24h", 0),
                kalshi_volume_24h=km.get("volume", 0) or 0,
                polymarket_slug=pm.get("slug", ""),
                kalshi_ticker=km.get("ticker", ""),
                settlement_risk=risk.warning,
                settlement_risk_level=risk.level,
                direction=spread["direction"],
            )
            opportunities.append(opp)

        opportunities.sort(key=lambda x: x.spread_pct, reverse=True)
        logger.info(f"Scanner: {len(opportunities)} actionable opportunities found")
        return opportunities
