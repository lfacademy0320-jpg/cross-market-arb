"""Signal quality filter for subscription-grade arbitrage alerts.

Filters out noise, false matches, and high-risk signals.
Only passes opportunities that meet ALL quality gates.
"""
from ..config import SpreadOpportunity


QUALITY_RULES = {
    "min_spread_pct": 3.0,
    "max_risk_level": "medium",
    "min_pm_volume": 1000,
    "min_title_length": 10,
    "exclude_keywords": [
        "2032 Presidential", "2028 nomination", "2028 presidential",
        "2040", "2050", "party will win",
    ],
    "require_keywords": [],
}


def passes_quality_gate(opp: SpreadOpportunity) -> tuple[bool, str]:
    """Check if an opportunity passes all quality gates.

    Returns (passed, reason_if_failed).
    """
    if opp.spread_pct < QUALITY_RULES["min_spread_pct"]:
        return False, f"spread {opp.spread_pct:.1f}% below minimum {QUALITY_RULES['min_spread_pct']}%"

    risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    max_allowed = risk_order.get(QUALITY_RULES["max_risk_level"], 1)
    actual = risk_order.get(opp.settlement_risk_level, 0)
    if actual > max_allowed:
        return False, f"risk level {opp.settlement_risk_level} exceeds max {QUALITY_RULES['max_risk_level']}"

    if opp.polymarket_volume_24h < QUALITY_RULES["min_pm_volume"]:
        return False, f"PM volume ${opp.polymarket_volume_24h:,.0f} below min ${QUALITY_RULES['min_pm_volume']:,}"

    combined = f"{opp.event_title} {opp.market_title}".lower()
    for kw in QUALITY_RULES["exclude_keywords"]:
        if kw.lower() in combined:
            return False, f"matched exclude keyword: {kw}"

    if len(opp.market_title) < QUALITY_RULES["min_title_length"]:
        return False, f"title too short ({len(opp.market_title)} chars)"

    return True, "passed"


def filter_signals(opportunities: list[SpreadOpportunity]) -> list[SpreadOpportunity]:
    """Filter raw opportunities to subscription-quality signals."""
    passed: list[SpreadOpportunity] = []
    for o in opportunities:
        ok, reason = passes_quality_gate(o)
        if ok:
            passed.append(o)
    return passed


def format_signal_message(opp: SpreadOpportunity) -> str:
    """Format a single signal for Telegram broadcast."""
    risk_emoji = {"low": "LOW", "medium": "MED", "high": "HIGH", "critical": "CRIT"}
    risk = risk_emoji.get(opp.settlement_risk_level, "?")
    return (
        f"[{risk}] {opp.spread_pct:.1f}% spread\n"
        f"Market: {opp.market_title[:100]}\n"
        f"PM: ${opp.polymarket_price:.4f} | Kalshi: ${opp.kalshi_price:.4f}\n"
        f"Direction: {opp.direction}\n"
        f"PM Vol: ${opp.polymarket_volume_24h:,.0f}\n"
        + (f"Risk: {opp.settlement_risk}\n" if opp.settlement_risk else "")
    )
