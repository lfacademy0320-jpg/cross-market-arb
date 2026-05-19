"""Polygon USDC Payment Monitor.

Watches a wallet address for incoming USDC deposits.
On detection, activates/extends the subscriber's subscription.

Supports two modes:
    1. Polling (default): check every N seconds via Polygonscan API
    2. Webhook: receive events from Alchemy/Infura (future)

Usage:
    python -m subscription.payment_monitor --watch
    python -m subscription.payment_monitor --once
"""
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
sys.path.insert(0, str(Path(__file__).parent.parent))

from subscription.engine import record_payment, add_subscriber, TIERS

POLYGONSCAN_API_KEY = os.getenv("POLYGONSCAN_API_KEY", "")
WALLET_ADDRESS = os.getenv("SUBSCRIPTION_WALLET", "")
USDC_CONTRACT = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
POLYGONSCAN_URL = "https://api.polygonscan.com/api"


async def fetch_usdc_transfers(address: str, api_key: str, start_block: int = 0) -> list[dict]:
    """Fetch USDC transfer events for an address."""
    params = {
        "module": "account",
        "action": "tokentx",
        "contractaddress": USDC_CONTRACT,
        "address": address,
        "page": 1,
        "offset": 50,
        "sort": "desc",
        "apikey": api_key,
    }
    if start_block > 0:
        params["startblock"] = start_block
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(POLYGONSCAN_URL, params=params)
            data = resp.json()
            if data.get("status") == "1":
                return data.get("result", [])
    except Exception as e:
        logger.error(f"Polygonscan API error: {e}")
    return []


def parse_amount(value: str, decimals: int = 6) -> float:
    """Parse USDC amount from raw value."""
    try:
        return float(value) / (10 ** decimals)
    except (ValueError, TypeError):
        return 0.0


def match_tier(amount: float) -> tuple[str, int]:
    """Match payment amount to subscription tier. Returns (tier, days)."""
    if amount >= 199:
        return "inst", 30
    elif amount >= 49:
        return "pro", 30
    elif amount >= 10:
        return "pro", 7  # weekly trial
    else:
        return "free", 0


def load_last_block(tracker_file: Path) -> int:
    """Load last processed block number."""
    try:
        data = json.loads(tracker_file.read_text())
        return data.get("last_block", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0


def save_last_block(tracker_file: Path, block: int):
    """Save last processed block number."""
    tracker_file.parent.mkdir(parents=True, exist_ok=True)
    tracker_file.write_text(json.dumps({"last_block": block, "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))


async def check_payments():
    """Check for new USDC payments and activate subscriptions."""
    if not POLYGONSCAN_API_KEY or not WALLET_ADDRESS:
        logger.warning("Payment monitor not configured (set POLYGONSCAN_API_KEY and SUBSCRIPTION_WALLET in .env)")
        return 0

    tracker_file = Path(__file__).parent / ".payment_tracker.json"
    last_block = load_last_block(tracker_file)

    transfers = await fetch_usdc_transfers(WALLET_ADDRESS, POLYGONSCAN_API_KEY, last_block)
    if not transfers:
        return 0

    new_payments = 0
    highest_block = last_block

    for tx in transfers:
        block = int(tx.get("blockNumber", 0))
        if block > highest_block:
            highest_block = block

        if tx.get("to", "").lower() != WALLET_ADDRESS.lower():
            continue

        tx_hash = tx.get("hash", "")
        amount = parse_amount(tx.get("value", "0"))
        from_addr = tx.get("from", "")

        if amount <= 0:
            continue

        tier, days = match_tier(amount)
        if tier == "free":
            logger.info(f"Ignoring small payment {amount} USDC from {from_addr[:10]}...")
            continue

        is_new = record_payment(tx_hash, from_addr, amount, tier)
        if not is_new:
            continue

        telegram_id = from_addr
        sub = add_subscriber(telegram_id, username=from_addr[:12], tier=tier,
                             duration_days=days, payment_tx=tx_hash)
        logger.success(f"New {tier} subscriber: {telegram_id[:12]}... ({amount} USDC, {days} days)")
        new_payments += 1

    if highest_block > last_block:
        save_last_block(tracker_file, highest_block)

    return new_payments


async def watch_loop(interval: int = 60):
    """Continuous payment monitoring loop."""
    logger.info(f"Payment monitor started (wallet={WALLET_ADDRESS[:10]}..., interval={interval}s)")
    while True:
        try:
            count = await check_payments()
            if count > 0:
                logger.info(f"Processed {count} new payment(s)")
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        await asyncio.sleep(interval)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring")
    parser.add_argument("--once", action="store_true", help="Single check")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()

    if args.watch:
        asyncio.run(watch_loop(args.interval))
    else:
        count = asyncio.run(check_payments())
        print(f"Processed {count} new payment(s)")


if __name__ == "__main__":
    main()
