"""Cross-platform event matching and spread calculation engine."""
from difflib import SequenceMatcher
from loguru import logger


def normalize_title(title: str) -> str:
    """Normalize event titles for comparison. Strips common prefixes, lowercases."""
    prefixes = [
        "Will ", "Will the ", "Will there be ",
        "Does ", "Is ", "Are ", "Has ", "Can ",
    ]
    t = title.strip().lower()
    for prefix in prefixes:
        if t.startswith(prefix.lower()):
            t = t[len(prefix):]
            break
    t = t.rstrip("?").strip()
    return t


def similarity(a: str, b: str) -> float:
    """Fuzzy match score between two event titles (0.0 to 1.0)."""
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def match_events(
    polymarket_markets: list[dict],
    kalshi_markets: list[dict],
    threshold: float = 0.55,
) -> list[tuple[dict, dict, float]]:
    """Match Polymarket and Kalshi markets by fuzzy title similarity.

    Returns sorted list of (pm_market, kalshi_market, similarity_score).
    """
    pairs: list[tuple[dict, dict, float]] = []

    for pm in polymarket_markets:
        pm_q = pm.get("question", "") or pm.get("title", "")
        if not pm_q:
            continue

        best_score = 0.0
        best_km = None
        for km in kalshi_markets:
            km_title = km.get("title", "")
            if not km_title:
                continue
            score = similarity(pm_q, km_title)
            if score > best_score:
                best_score = score
                best_km = km

        if best_km and best_score >= threshold:
            pairs.append((pm, best_km, best_score))

    pairs.sort(key=lambda x: x[2], reverse=True)
    logger.info(f"Comparator: matched {len(pairs)} event pairs (threshold={threshold})")
    return pairs


def calculate_spread(
    pm_price: float,
    kalshi_price: float,
) -> dict:
    """Calculate cross-platform spread opportunity.

    Returns dict with spread_pct, direction, and actionable flag.
    Direction: 'buy_pm_sell_kalshi' means PM is cheaper, buy on PM.
               'buy_kalshi_sell_pm' means Kalshi is cheaper, buy on Kalshi.
    """
    if pm_price <= 0 or kalshi_price <= 0 or pm_price >= 1 or kalshi_price >= 1:
        return {"spread_pct": 0, "direction": "none", "actionable": False}

    diff = pm_price - kalshi_price
    spread_pct = abs(diff) * 100

    if diff < 0:
        direction = "buy_pm_sell_kalshi"
    elif diff > 0:
        direction = "buy_kalshi_sell_pm"
    else:
        direction = "none"

    actionable = spread_pct >= 1.0

    return {
        "spread_pct": round(spread_pct, 2),
        "direction": direction,
        "actionable": actionable,
    }


def estimate_profit(
    spread_pct: float,
    capital: float = 1000.0,
    fees: float = 0.01,
) -> dict:
    """Estimate net profit after platform fees and gas."""
    gross = capital * (spread_pct / 100)
    net = gross - (capital * fees * 2)
    return {
        "capital": capital,
        "gross_profit": round(gross, 2),
        "fees": round(capital * fees * 2, 2),
        "net_profit": round(net, 2),
        "roi_pct": round((net / capital) * 100, 2),
    }
