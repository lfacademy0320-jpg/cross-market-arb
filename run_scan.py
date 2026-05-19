#!/usr/bin/env python3
"""Cross-Platform Arbitrage Scanner — CLI entry point.

Scans Polymarket and Kalshi for same-event pricing discrepancies,
outputs ranked opportunities with settlement risk warnings.

Usage:
    python run_scan.py                  # Quick scan (top 100 markets)
    python run_scan.py --deep           # Deep scan (top 500 markets)
    python run_scan.py --json           # JSON output
    python run_scan.py --report         # Save Markdown report
"""
import argparse
import asyncio
from loguru import logger

from src.config import ScanSettings
from src.strategy.scanner import CrossPlatformScanner
from src.output.alert import format_opportunities_table, format_opportunities_json, send_telegram_alert
from src.output.report import save_json_report, save_markdown_report


async def main():
    parser = argparse.ArgumentParser(description="Polymarket-Kalshi Cross-Platform Arbitrage Scanner")
    parser.add_argument("--deep", action="store_true", help="Deep scan (500 markets)")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    parser.add_argument("--report", action="store_true", help="Save Markdown report")
    parser.add_argument("--min-spread", type=float, default=1.0, help="Minimum spread %% to report")
    parser.add_argument("--threshold", type=float, default=0.55, help="Fuzzy match threshold (0.0-1.0)")
    parser.add_argument("--telegram", action="store_true", help="Send Telegram alert")
    args = parser.parse_args()

    settings = ScanSettings()
    if args.min_spread:
        settings.min_profit_percent = args.min_spread
    if args.deep:
        settings.max_scan_markets = 500

    logger.info(f"Starting cross-platform scan (max markets: {settings.max_scan_markets}, min spread: {settings.min_profit_percent}%)")

    scanner = CrossPlatformScanner(settings)
    try:
        opportunities = await scanner.scan(match_threshold=args.threshold)

        if args.json:
            from src.output.alert import format_opportunities_json
            print(format_opportunities_json(opportunities))
        else:
            print(format_opportunities_table(opportunities))

        if args.report:
            path = save_markdown_report(opportunities)
            logger.info(f"Markdown report: {path}")

        if args.telegram and settings.telegram_bot_token and settings.telegram_chat_id:
            await send_telegram_alert(opportunities, settings.telegram_bot_token, settings.telegram_chat_id)

        if opportunities:
            logger.success(
                f"Top opportunity: {opportunities[0].spread_pct:.1f}% spread — {opportunities[0].market_title[:60]}"
            )
        else:
            logger.info("No actionable opportunities found in this scan.")

    finally:
        await scanner.close()


if __name__ == "__main__":
    asyncio.run(main())
