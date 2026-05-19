#!/usr/bin/env python3
"""Arbitrage Signal Daemon - Scheduled scanner + Telegram broadcast.

Runs cross-platform scans on a configurable interval, filters quality
signals, and broadcasts to Telegram. Designed for subscription service.

Usage:
    python signal_daemon.py                     # Run once
    python signal_daemon.py --interval 300      # Scan every 5 minutes
    python signal_daemon.py --once --json       # Single scan, JSON output
"""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from src.config import ScanSettings
from src.strategy.scanner import CrossPlatformScanner
from src.output.signal_filter import filter_signals, format_signal_message, QUALITY_RULES

SIGNALS_LOG = Path(__file__).parent / "signals.jsonl"


async def broadcast_telegram(messages: list[str], bot_token: str, chat_id: str):
    """Send signal messages to Telegram channel."""
    if not bot_token or not chat_id:
        return
    async with httpx.AsyncClient() as client:
        for msg in messages:
            try:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                    timeout=10,
                )
            except Exception as e:
                logger.warning(f"Telegram send failed: {e}")


def log_signal(opportunity):
    """Append signal to JSONL log for historical tracking."""
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "spread_pct": opportunity.spread_pct,
        "pm_price": opportunity.polymarket_price,
        "ks_price": opportunity.kalshi_price,
        "direction": opportunity.direction,
        "market": opportunity.market_title,
        "risk": opportunity.settlement_risk_level,
    }
    with open(SIGNALS_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


async def run_once(settings: ScanSettings, broadcast: bool = False) -> int:
    """Single scan cycle. Returns number of quality signals found."""
    scanner = CrossPlatformScanner(settings)
    try:
        opportunities = await scanner.scan(match_threshold=0.50)
        signals = filter_signals(opportunities)

        if signals:
            logger.success(f"Quality signals: {len(signals)}/{len(opportunities)}")
            messages = [format_signal_message(s) for s in signals[:5]]
            for msg in messages:
                print(msg)
                print("---")

            if broadcast:
                bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
                chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
                await broadcast_telegram(messages, bot_token, chat_id)

            for s in signals:
                log_signal(s)
        else:
            logger.info(f"No quality signals ({len(opportunities)} raw opps filtered)")

        return len(signals)
    finally:
        await scanner.close()


async def run_loop(interval: int, settings: ScanSettings, broadcast: bool = False):
    """Continuous scanning loop."""
    logger.info(f"Signal daemon started (interval={interval}s, min_spread={settings.min_profit_percent}%)")
    while True:
        try:
            count = await run_once(settings, broadcast=broadcast)
            if count > 0:
                logger.info(f"Next scan in {interval}s")
            await asyncio.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Daemon stopped")
            break
        except Exception as e:
            logger.error(f"Scan error: {e}")
            await asyncio.sleep(30)


def main():
    parser = argparse.ArgumentParser(description="Arbitrage Signal Daemon")
    parser.add_argument("--interval", type=int, default=0, help="Scan interval in seconds (0 = run once)")
    parser.add_argument("--once", action="store_true", help="Single scan and exit")
    parser.add_argument("--broadcast", action="store_true", help="Send signals to Telegram")
    parser.add_argument("--json", action="store_true", help="JSON output mode")
    parser.add_argument("--min-spread", type=float, default=3.0, help="Minimum spread %% for quality signals")
    parser.add_argument("--deep", action="store_true", help="Deep scan (200 markets)")
    args = parser.parse_args()

    settings = ScanSettings()
    settings.min_profit_percent = args.min_spread
    if args.deep:
        settings.max_scan_markets = 200

    if args.json:
        import asyncio as aio
        async def json_run():
            s = CrossPlatformScanner(settings)
            try:
                opps = await s.scan(match_threshold=0.50)
                signals = filter_signals(opps)
                print(json.dumps([o.model_dump() for o in signals], indent=2, default=str))
            finally:
                await s.close()
        aio.run(json_run())
        return

    if args.interval > 0:
        asyncio.run(run_loop(args.interval, settings, broadcast=args.broadcast))
    else:
        asyncio.run(run_once(settings, broadcast=args.broadcast))


if __name__ == "__main__":
    main()
