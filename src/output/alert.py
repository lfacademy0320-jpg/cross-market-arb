"""Console and Telegram alert output."""
import json
from loguru import logger
from ..config import SpreadOpportunity


def format_opportunities_table(opportunities: list[SpreadOpportunity]) -> str:
    """Format opportunities as a human-readable table."""
    if not opportunities:
        return "No cross-platform arbitrage opportunities found."

    lines = [
        "",
        "═" * 90,
        "  CROSS-PLATFORM ARBITRAGE OPPORTUNITIES",
        "  Polymarket ↔ Kalshi",
        "═" * 90,
        "",
    ]

    for i, o in enumerate(opportunities[:10], 1):
        risk_icon = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(
            o.settlement_risk_level, "⚪"
        )

        lines.append(f"  #{i}  {o.market_title[:80]}")
        lines.append(f"      PM: ${o.polymarket_price:.4f}  │  Kalshi: ${o.kalshi_price:.4f}  │  Spread: {o.spread_pct:.1f}%")
        lines.append(f"      Direction: {o.direction}  │  PM Vol: ${o.polymarket_volume_24h:,.0f}  │  Risk: {risk_icon} {o.settlement_risk_level}")
        if o.settlement_risk:
            lines.append(f"      ⚠ {o.settlement_risk}")
        lines.append("")

    lines.append("═" * 90)
    return "\n".join(lines)


def format_opportunities_json(opportunities: list[SpreadOpportunity]) -> str:
    """Format opportunities as JSON for piping or webhook."""
    return json.dumps(
        [o.model_dump() for o in opportunities],
        indent=2,
        ensure_ascii=False,
    )


async def send_telegram_alert(opportunities: list[SpreadOpportunity], bot_token: str, chat_id: str):
    """Send top opportunities to Telegram."""
    if not bot_token or not chat_id or not opportunities:
        return

    import httpx
    top = opportunities[:5]
    lines = ["🔔 *Cross-Platform Arb Alerts*", ""]
    for o in top:
        risk_icon = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(
            o.settlement_risk_level, "⚪"
        )
        lines.append(f"{risk_icon} *{o.spread_pct:.1f}%* - {o.market_title[:60]}")
        lines.append(f"  PM ${o.polymarket_price:.4f} | Kalshi ${o.kalshi_price:.4f} | {o.direction}")
        if o.settlement_risk:
            lines.append(f"  ⚠ {o.settlement_risk[:120]}")

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": "\n".join(lines),
                    "parse_mode": "Markdown",
                },
            )
    except Exception as e:
        logger.warning(f"Telegram alert failed: {e}")
