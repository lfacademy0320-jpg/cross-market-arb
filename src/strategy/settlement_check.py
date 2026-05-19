"""Settlement rule divergence detection.

The #1 killer of cross-platform arbitrage: different platforms define
the same event differently, so one side settles YES and the other NO.
"""
from dataclasses import dataclass
from loguru import logger


@dataclass
class SettlementRisk:
    level: str  # "low", "medium", "high", "critical"
    warning: str
    source_mismatch: str = ""


KNOWN_DIVERGENCE_PATTERNS: list[dict] = [
    {
        "keywords": ["government shutdown", "shutdown", "spending bill"],
        "risk": "high",
        "reason": "Platforms disagree on what constitutes a shutdown: Polymarket uses 'OPM issues shutdown memo', Kalshi requires 'actual shutdown lasting >24 hours'.",
    },
    {
        "keywords": ["ceasefire", "peace deal", "peace agreement"],
        "risk": "high",
        "reason": "Settlement definitions vary widely: 'temporary ceasefire', 'permanent peace', 'cessation of hostilities' are different outcomes.",
    },
    {
        "keywords": ["recession", "economic contraction", "gdp"],
        "risk": "medium",
        "reason": "NBER declaration timing vs technical definition (2 consecutive quarters) can differ by months.",
    },
    {
        "keywords": ["layoff", "layoffs", "job cuts"],
        "risk": "medium",
        "reason": "Counting methodology varies: announced vs executed, full-time vs contractors, specific company scope.",
    },
    {
        "keywords": ["election", "primary", "nominee", "president"],
        "risk": "medium",
        "reason": "Resolution sources may differ (AP call vs certified results). Timing of resolution can vary by days.",
    },
    {
        "keywords": ["bitcoin", "btc", "ethereum", "eth", "crypto price"],
        "risk": "low",
        "reason": "Index price feeds may differ slightly between platforms.",
    },
    {
        "keywords": ["interest rate", "fed", "federal reserve", "rate cut"],
        "risk": "low",
        "reason": "Event definition usually tight (specific FOMC meeting), but timing of settlement can differ by hours.",
    },
]


def check_settlement_risk(market_title: str, event_title: str = "") -> SettlementRisk:
    """Check a market pair for known settlement rule divergence patterns."""
    combined = f"{event_title} {market_title}".lower()

    for pattern in KNOWN_DIVERGENCE_PATTERNS:
        if any(kw in combined for kw in pattern["keywords"]):
            return SettlementRisk(
                level=pattern["risk"],
                warning=pattern["reason"],
            )

    return SettlementRisk(level="low", warning="")


def flag_high_risk_pairs(matched_pairs: list, threshold: str = "medium") -> list[dict]:
    """Filter matched pairs to only those with settlement risk at or above threshold."""
    risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    flagged = []

    for pm, km, score in matched_pairs:
        risk = check_settlement_risk(
            pm.get("question", "") or pm.get("title", ""),
            pm.get("event_title", ""),
        )
        if risk_order.get(risk.level, 0) >= risk_order.get(threshold, 1):
            flagged.append({
                "polymarket_market": pm,
                "kalshi_market": km,
                "similarity": score,
                "risk": risk,
            })

    logger.info(f"SettlementCheck: {len(flagged)} pairs flagged with {threshold}+ risk")
    return flagged
