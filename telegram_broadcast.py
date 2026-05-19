#!/usr/bin/env python3
"""Telegram Broadcast Bot for Paid Signal Subscribers.

Manages subscriber list, sends quality-filtered signals to paid channel.
Supports free tier (delayed) and pro tier (real-time).

Setup:
    1. Create a Telegram channel
    2. Create a bot via @BotFather, get token
    3. Add bot as admin to channel
    4. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID in .env

Usage:
    python telegram_broadcast.py --test       # Send test message
    python telegram_broadcast.py --daemon     # Run continuous broadcast loop
"""
import argparse
import asyncio
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
from src.output.signal_filter import filter_signals, format_signal_message

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
FREE_CHANNEL_ID = os.getenv("TELEGRAM_FREE_CHANNEL_ID", "")


async def send_message(text: str, token: str, chat_id: str, premium: bool = True) -> bool:
    """Send a message to a Telegram channel."""
    if not token or not chat_id:
        logger.warning("Telegram not configured")
        return False
    prefix = "[ArbSignal PRO]" if premium else "[ArbSignal FREE - 24h delayed]"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": f"{prefix}\n{text}"},
                timeout=10,
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


async def broadcast_cycle(premium: bool = True):
    """One full scan + broadcast cycle."""
    settings = ScanSettings()
    scanner = CrossPlatformScanner(settings)
    try:
        opportunities = await scanner.scan(match_threshold=0.50)
        signals = filter_signals(opportunities)

        if not signals:
            logger.info("No quality signals this cycle")
            return 0

        token = BOT_TOKEN
        chat_id = CHANNEL_ID if premium else FREE_CHANNEL_ID

        sent = 0
        for signal in signals[:3]:
            msg = format_signal_message(signal)
            if premium:
                ok = await send_message(msg, token, chat_id, premium=True)
            else:
                ok = await send_message(msg, token, chat_id, premium=False)
            if ok:
                sent += 1
            await asyncio.sleep(1)

        logger.info(f"Broadcast: {sent}/{len(signals)} sent ({'premium' if premium else 'free'})")
        return sent
    finally:
        await scanner.close()


async def daemon_loop(interval: int = 600):
    """Continuous broadcast daemon."""
    logger.info(f"Broadcast daemon started (interval={interval}s)")
    while True:
        try:
            await broadcast_cycle(premium=True)
            await asyncio.sleep(interval)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Cycle error: {e}")
            await asyncio.sleep(60)


async def send_test():
    """Send a test message to verify Telegram configuration."""
    ok = await send_message(
        "Test message from ArbSignal broadcast system. If you see this, Telegram is configured correctly.",
        BOT_TOKEN, CHANNEL_ID,
    )
    print("Test message sent!" if ok else "Failed to send test message.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--interval", type=int, default=600)
    parser.add_argument("--free", action="store_true", help="Send to free channel")
    args = parser.parse_args()

    if args.test:
        asyncio.run(send_test())
    elif args.daemon:
        asyncio.run(daemon_loop(args.interval))
    else:
        asyncio.run(broadcast_cycle(premium=not args.free))


if __name__ == "__main__":
    main()
