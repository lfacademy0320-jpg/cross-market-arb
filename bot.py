#!/usr/bin/env python3
"""ArbSignal Telegram Bot - Single entry point for the entire platform.

Handles: user commands, subscription management, signal delivery, payment flow.
Runs 24/7 when deployed to any server or GitHub Actions scheduled runner.

Commands:
    /start      - Welcome + pricing
    /subscribe  - Payment instructions
    /status     - Your subscription status
    /signals    - Latest signals (tier-gated)
    /help       - All commands

Deploy:
    python bot.py                     # Run once (for GitHub Actions)
    python bot.py --poll              # Polling mode (long-running server)
"""
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
from subscription.engine import (
    init_db, add_subscriber, get_subscriber, get_subscriber_count,
    deactivate_expired, list_active_subscribers,
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "ArbSignalBot")

PRICING_MESSAGE = """
*ArbSignal - Cross-Platform Arbitrage Alerts*

*Free* ($0/mo)
- 1 daily summary (24hr delayed)

*Pro* ($49/mo)
- Real-time signals every 10 min
- Up to 5 signals per cycle
- Settlement risk analysis
- Telegram DM delivery

*Institutional* ($199/mo)
- 1-minute scan interval
- Unlimited signals
- API access
- Priority support

Pay with USDC (Polygon):
`0x...YOUR_WALLET...`

After payment, send your TX hash to activate.
""".strip()


async def send_message(chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Send failed: {e}")
        return False


async def handle_start(chat_id: str, username: str = ""):
    sub = get_subscriber(str(chat_id))
    if not sub:
        add_subscriber(str(chat_id), username, "free", 0, "")
        sub = get_subscriber(str(chat_id))

    tier = sub.tier if sub else "free"
    expiry = sub.expires_at[:10] if sub and sub.expires_at else "N/A"

    msg = f"Welcome to ArbSignal, {username or 'trader'}!\n\n"
    msg += f"Your tier: *{tier.upper()}*\n"
    msg += f"Expires: {expiry}\n\n"
    msg += "Use /signals for latest opportunities\n"
    msg += "Use /subscribe to upgrade\n"
    msg += "Use /status to check your subscription"

    await send_message(chat_id, msg)


async def handle_subscribe(chat_id: str):
    msg = (
        "*Subscribe to ArbSignal Pro*\n\n"
        "1. Send *$49 USDC* (Polygon) to:\n"
        "   `0x...YOUR_WALLET...`\n\n"
        "2. Send your transaction hash here:\n"
        "   `/activate 0x...tx_hash`\n\n"
        "Your Pro subscription activates instantly.\n\n"
        "*Inst ($199/mo)*: send $199 USDC instead."
    )
    await send_message(chat_id, msg)


async def handle_activate(chat_id: str, tx_hash: str):
    from subscription.payment_monitor import check_payments
    msg = (
        f"Activation requested with TX: `{tx_hash}`\n\n"
        "Our payment monitor checks every 60 seconds.\n"
        "You will receive a confirmation once verified.\n\n"
        "Check status: /status"
    )
    await send_message(chat_id, msg)


async def handle_status(chat_id: str):
    sub = get_subscriber(str(chat_id))
    if not sub:
        await send_message(chat_id, "No subscription found. Use /start to begin.")
        return

    from subscription.engine import TIERS
    tier_cfg = TIERS.get(sub.tier, TIERS["free"])

    msg = (
        f"*Your Subscription*\n\n"
        f"Tier: *{sub.tier.upper()}*\n"
        f"Price: ${tier_cfg['price']}/mo\n"
        f"Expires: {sub.expires_at[:10]}\n"
        f"Scan interval: {tier_cfg['interval']}s\n"
        f"Max signals: {tier_cfg['max_signals']}/cycle\n"
        f"Status: {'ACTIVE' if sub.active else 'INACTIVE'}"
    )
    await send_message(chat_id, msg)


async def handle_signals(chat_id: str):
    sub = get_subscriber(str(chat_id))
    if not sub or not sub.active:
        await send_message(chat_id, "No active subscription. Use /subscribe to get signals.")
        return

    from subscription.engine import TIERS
    tier_cfg = TIERS.get(sub.tier, TIERS["free"])

    await send_message(chat_id, "Scanning markets...")

    settings = ScanSettings()
    scanner = CrossPlatformScanner(settings)
    try:
        opportunities = await scanner.scan(match_threshold=0.50)
        signals = filter_signals(opportunities)
    finally:
        await scanner.close()

    if not signals:
        await send_message(chat_id, "No quality signals right now. Markets efficient.")
        return

    selected = signals[:tier_cfg["max_signals"]]
    for s in selected:
        msg = format_signal_message(s)
        await send_message(chat_id, msg)
        await asyncio.sleep(0.3)

    await send_message(chat_id, f"_{len(signals)} total signals, showing top {len(selected)} ({sub.tier})_")


async def handle_help(chat_id: str):
    msg = (
        "*ArbSignal Commands*\n\n"
        "/start - Welcome + setup\n"
        "/subscribe - Upgrade to Pro\n"
        "/signals - Latest arbitrage signals\n"
        "/status - Your subscription\n"
        "/help - This message\n\n"
        "Pro subscribers receive real-time signals via DM."
    )
    await send_message(chat_id, msg)


async def process_update(update: dict):
    """Process a single Telegram update."""
    msg = update.get("message", {})
    chat = msg.get("chat", {})
    chat_id = str(chat.get("id", ""))
    text = msg.get("text", "").strip()
    username = msg.get("from", {}).get("username", "") or msg.get("from", {}).get("first_name", "")

    if not chat_id or not text:
        return

    logger.info(f"@{username} ({chat_id}): {text[:60]}")

    if text.startswith("/start"):
        await handle_start(chat_id, username)
    elif text.startswith("/subscribe"):
        await handle_subscribe(chat_id)
    elif text.startswith("/activate"):
        parts = text.split()
        tx_hash = parts[1] if len(parts) > 1 else ""
        await handle_activate(chat_id, tx_hash)
    elif text.startswith("/status"):
        await handle_status(chat_id)
    elif text.startswith("/signals"):
        await handle_signals(chat_id)
    elif text.startswith("/help"):
        await handle_help(chat_id)
    else:
        await send_message(chat_id, "Use /start to begin or /help for commands.")


async def poll_updates(interval: int = 3):
    """Long-polling mode - fetch updates from Telegram continuously."""
    logger.info(f"Bot @{BOT_USERNAME} starting poll mode (interval={interval}s)")
    init_db()

    offset = 0
    while True:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                )
                data = resp.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        await process_update(update)
        except KeyboardInterrupt:
            logger.info("Bot stopped")
            break
        except Exception as e:
            logger.error(f"Poll error: {e}")
        await asyncio.sleep(interval)


async def run_once():
    """Single run mode - for GitHub Actions: scan + deliver + check payments."""
    init_db()
    deactivate_expired()

    # Run scanner
    settings = ScanSettings()
    scanner = CrossPlatformScanner(settings)
    try:
        opportunities = await scanner.scan(match_threshold=0.50)
        signals = filter_signals(opportunities)
    finally:
        await scanner.close()

    if signals:
        subscribers = list_active_subscribers()
        paid = [s for s in subscribers if s.tier in ("pro", "inst")]
        logger.info(f"Signals: {len(signals)} | Paid subscribers: {len(paid)}")

        for sub in paid:
            from subscription.engine import TIERS
            tier_cfg = TIERS.get(sub.tier, TIERS["free"])
            selected = signals[:tier_cfg["max_signals"]]
            for s in selected:
                msg = format_signal_message(s)
                await send_message(sub.telegram_id, msg)
                await asyncio.sleep(0.3)

    # Check payments
    from subscription.payment_monitor import check_payments
    await check_payments()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ArbSignal Telegram Bot")
    parser.add_argument("--poll", action="store_true", help="Long-polling mode (server)")
    parser.add_argument("--once", action="store_true", help="Single run (GitHub Actions)")
    parser.add_argument("--webhook", type=str, default="", help="Webhook URL (alternative to polling)")
    args = parser.parse_args()

    if args.poll:
        asyncio.run(poll_updates())
    else:
        count = asyncio.run(run_once())
        logger.info(f"Bot cycle complete. Signals delivered.")


if __name__ == "__main__":
    main()
