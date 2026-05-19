"""JSON and Markdown report file generation."""
import json
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger
from ..config import SpreadOpportunity


def save_json_report(
    opportunities: list[SpreadOpportunity],
    output_dir: str = ".",
) -> str:
    """Save opportunities as a timestamped JSON report. Returns file path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = Path(output_dir) / f"arb_scan_{ts}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "total_opportunities": len(opportunities),
        "opportunities": [o.model_dump() for o in opportunities],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    logger.info(f"Report saved to {path}")
    return str(path)


def save_markdown_report(
    opportunities: list[SpreadOpportunity],
    output_dir: str = ".",
) -> str:
    """Save opportunities as a timestamped Markdown report. Returns file path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = Path(output_dir) / f"arb_scan_{ts}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Cross-Platform Arbitrage Scan",
        f"",
        f"**Scanned:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Platforms:** Polymarket <-> Kalshi",
        f"**Opportunities found:** {len(opportunities)}",
        f"",
        f"---",
        f"",
    ]

    if not opportunities:
        lines.append("_No actionable opportunities found._")
    else:
        lines.append(f"| # | Spread | PM Price | Kalshi Price | Market | Risk |")
        lines.append(f"|---|--------|----------|--------------|--------|------|")
        for i, o in enumerate(opportunities[:20], 1):
            risk_icon = {"low": "[LOW]", "medium": "[MED]", "high": "[HIGH]", "critical": "[CRIT]"}.get(
                o.settlement_risk_level, "[?]"
            )
            lines.append(
                f"| {i} | **{o.spread_pct:.1f}%** | {o.polymarket_price:.4f} | "
                f"{o.kalshi_price:.4f} | {o.market_title[:50]} | {risk_icon} {o.settlement_risk_level} |"
            )

        lines.append("")
        lines.append("## Top Opportunities Detail")
        lines.append("")
        for i, o in enumerate(opportunities[:5], 1):
            lines.append(f"### #{i} - {o.market_title}")
            lines.append(f"- **Spread:** {o.spread_pct:.1f}%")
            lines.append(f"- **Direction:** {o.direction}")
            lines.append(f"- **PM Price:** ${o.polymarket_price:.4f} | **Kalshi Price:** ${o.kalshi_price:.4f}")
            lines.append(f"- **PM Volume 24h:** ${o.polymarket_volume_24h:,.0f} | **Kalshi Volume 24h:** ${o.kalshi_volume_24h:,.0f}")
            if o.settlement_risk:
                lines.append(f"- **⚠ Settlement Risk:** {o.settlement_risk}")
            lines.append("")

    path.write_text("\n".join(lines))
    logger.info(f"Markdown report saved to {path}")
    return str(path)
