#!/usr/bin/env python3
"""Telegram Broadcast Bot for Paid Signal Subscribers.

Now integrated with subscription engine for tier-gated delivery.

Setup:
    1. Create bot via @BotFather, get token → set TELEGRAM_BOT_TOKEN in .env
    2. Create paid channel → set TELEGRAM_CHANNEL_ID in .env
    3. Add subscribers via: python -m subscription.cli add <telegram_id> <tier>
    4. Run: python telegram_broadcast.py --daemon

Tiers:
    free - broadcast to free channel only (24hr delayed)
    pro  - DM signals to pro subscribers (real-time)
    inst - DM signals + API access (real-time)
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from loguru import logger

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from src.config import ScanSettings
from src.strategy.scanner import CrossPlatformScanner
from src.output.signal_filter import filter_signals, format_signal_message
from subscription.engine import list_active_subscribers, deactivate_expired, TIERS

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")


async def send_dm(telegram_id: str, text: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": telegram_id, "text": text},
            )
            return resp.status_code == 200
    except Exception:
        return False


async def broadcast_cycle():
    deactivate_expired()
    subscribers = list_active_subscribers()
    paid = [s for s in subscribers if s.tier in ("pro", "inst")]

    if not paid:
        logger.info("No paid subscribers")
        return 0

    settings = ScanSettings()
    scanner = CrossPlatformScanner(settings)
    try:
        opportunities = await scanner.scan(match_threshold=0.50)
        signals = filter_signals(opportunities)
    finally:
        await scanner.close()

    sent = 0
    for sub in paid:
        tier_cfg = TIERS.get(sub.tier, TIERS["free"])
        selected = signals[:tier_cfg["max_signals"]]
        lines = [f"ArbSignal {sub.tier.upper()} | {sub.expires_at[:10]}", ""]
        for s in selected:
            lines.append(format_signal_message(s))
            lines.append("---")
        if not selected:
            lines.append("No signals this cycle.")
        if await send_dm(sub.telegram_id, "\n".join(lines)):
            sent += 1
        await asyncio.sleep(0.3)

    logger.info(f"Broadcast: {sent}/{len(paid)} subscribers received signals")
    return sent


async def daemon_loop(interval: int = 600):
    logger.info(f"Broadcast daemon started (interval={interval}s, targeting paid subscribers)")
    while True:
        try:
            await broadcast_cycle()
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Cycle error: {e}")
        await asyncio.sleep(interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=600)
    args = parser.parse_args()

    if args.daemon:
        asyncio.run(daemon_loop(args.interval))
    else:
        count = asyncio.run(broadcast_cycle())
        print(f"Broadcast complete: {count} subscribers received signals")


if __name__ == "__main__":
    main()
