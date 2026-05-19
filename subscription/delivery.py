"""Tiered Signal Delivery System.

Delivers arbitrage signals to subscribers based on their tier:
  free: 24hr delayed, 1 daily summary via email-like format
  pro:  real-time, up to 5 signals per cycle, Telegram DM
  inst: real-time, unlimited, API + Telegram

The delivery engine gates signal access by subscriber tier and expiry.
"""
import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from loguru import logger

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import ScanSettings, SpreadOpportunity
from src.strategy.scanner import CrossPlatformScanner
from src.output.signal_filter import filter_signals, format_signal_message
from subscription.engine import list_active_subscribers, deactivate_expired, get_subscriber, TIERS

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


async def send_dm(telegram_id: str, text: str, token: str) -> bool:
    """Send a direct message to a Telegram user."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": telegram_id, "text": text},
            )
            return resp.status_code == 200
    except Exception as e:
        logger.warning(f"DM to {telegram_id} failed: {e}")
        return False


async def deliver_to_subscriber(subscriber, signals: list[SpreadOpportunity],
                                token: str, cycle_ts: str) -> bool:
    """Deliver signals to one subscriber based on their tier."""
    tier_cfg = TIERS.get(subscriber.tier, TIERS["free"])

    if tier_cfg["delay_hours"] > 0:
        return False

    max_signals = tier_cfg["max_signals"]
    selected = signals[:max_signals]

    lines = [f"ArbSignal {subscriber.tier.upper()} | {cycle_ts}", ""]
    for s in selected:
        lines.append(format_signal_message(s))
        lines.append("---")

    if not selected:
        lines.append("No quality signals this cycle. Markets are efficient right now.")

    lines.append(f"Subscription: {subscriber.tier} | Expires: {subscriber.expires_at[:10]}")

    return await send_dm(subscriber.telegram_id, "\n".join(lines), token)


async def run_delivery_cycle():
    """One complete delivery cycle across all active subscribers."""
    deactivate_expired()

    subscribers = list_active_subscribers()
    paid = [s for s in subscribers if s.tier in ("pro", "inst")]
    if not paid:
        logger.info("No paid subscribers to deliver to")
        return 0

    settings = ScanSettings()
    scanner = CrossPlatformScanner(settings)
    try:
        opportunities = await scanner.scan(match_threshold=0.50)
        signals = filter_signals(opportunities)
    finally:
        await scanner.close()

    cycle_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sent = 0
    for sub in paid:
        try:
            ok = await deliver_to_subscriber(sub, signals, BOT_TOKEN, cycle_ts)
            if ok:
                sent += 1
        except Exception as e:
            logger.error(f"Delivery failed for {sub.telegram_id}: {e}")
        await asyncio.sleep(0.5)

    logger.info(f"Delivery cycle: {sent}/{len(paid)} subscribers, {len(signals)} signals")
    return sent


async def delivery_loop(interval: int = 600):
    """Continuous delivery daemon."""
    logger.info(f"Delivery daemon started (interval={interval}s)")
    while True:
        try:
            await run_delivery_cycle()
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Delivery cycle error: {e}")
        await asyncio.sleep(interval)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--interval", type=int, default=600)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if args.daemon:
        asyncio.run(delivery_loop(args.interval))
    else:
        count = asyncio.run(run_delivery_cycle())
        print(f"Delivered to {count} subscribers")


if __name__ == "__main__":
    main()
