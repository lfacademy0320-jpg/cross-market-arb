"""Main cross-platform arbitrage scanner orchestration."""
import asyncio
from loguru import logger

from ..config import ScanSettings, SpreadOpportunity
from ..data.polymarket import PolymarketClient
from ..data.kalshi import KalshiClient
from ..data.comparator import match_events, calculate_spread, estimate_profit
from ..strategy.settlement_check import check_settlement_risk


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
        """Run a full cross-platform scan and return ranked opportunities."""
        pm_markets = await self.polymarket.list_markets(
            limit=self.settings.max_scan_markets,
            volume_num_min=self.settings.min_volume_24h,
        )
        logger.info(f"Polymarket: {len(pm_markets)} markets loaded")

        km_markets = await self.kalshi.list_markets(limit=self.settings.max_scan_markets)
        logger.info(f"Kalshi: {len(km_markets)} markets loaded")

        pairs = match_events(pm_markets, km_markets, threshold=match_threshold)

        opportunities: list[SpreadOpportunity] = []
        for pm, km, score in pairs:
            pm_price = pm.get("midpoint", 0.5) or 0.5
            titles = km.get("yes_sub_title", "").lower()
            if "yes" in titles:
                km_price = float(km.get("yes_bid", 0.5) or 0.5)
            else:
                km_price = float(km.get("yes_bid", 0.5) or 0.5)

            spread = calculate_spread(pm_price, km_price)
            if not spread["actionable"] or spread["spread_pct"] < self.settings.min_profit_percent:
                continue

            risk = check_settlement_risk(
                pm.get("question", ""),
                pm.get("title", ""),
            )

            opp = SpreadOpportunity(
                event_title=pm.get("title", "") or pm.get("event_title", ""),
                market_title=pm.get("question", km.get("title", "")),
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
