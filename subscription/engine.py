"""Subscription Engine - Core subscriber management.

Handles: subscriber CRUD, tier management, expiry tracking, access gating.
Storage: SQLite (portable, zero-config).

Tiers:
    free     - $0/mo, 24hr delayed, 1 daily summary
    pro      - $49/mo, real-time signals, 10-min interval
    inst     - $199/mo, API access, raw data feed
"""
import json
import sqlite3
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "subscribers.db"

TIERS = {
    "free": {"price": 0, "interval": 86400, "max_signals": 1, "delay_hours": 24, "api": False},
    "pro": {"price": 49, "interval": 600, "max_signals": 5, "delay_hours": 0, "api": False},
    "inst": {"price": 199, "interval": 60, "max_signals": 999, "delay_hours": 0, "api": True},
}


@dataclass
class Subscriber:
    id: int = 0
    telegram_id: str = ""
    username: str = ""
    tier: str = "free"
    expires_at: str = ""
    created_at: str = ""
    active: bool = True
    payment_tx: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _expires_iso(days: int = 30) -> str:
    from datetime import timedelta
    dt = datetime.now(timezone.utc) + timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT UNIQUE NOT NULL,
            username TEXT DEFAULT '',
            tier TEXT DEFAULT 'free',
            expires_at TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            payment_tx TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_hash TEXT UNIQUE NOT NULL,
            from_address TEXT DEFAULT '',
            amount_usdc REAL DEFAULT 0,
            tier TEXT DEFAULT 'pro',
            processed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


def add_subscriber(telegram_id: str, username: str = "", tier: str = "free",
                   duration_days: int = 30, payment_tx: str = "") -> Subscriber:
    """Add or upgrade a subscriber. If exists, extends expiry."""
    init_db()
    conn = _connect()
    existing = conn.execute(
        "SELECT * FROM subscribers WHERE telegram_id = ?", (telegram_id,)
    ).fetchone()

    if existing:
        current_expiry = existing["expires_at"]
        new_expiry = _expires_iso(duration_days)
        conn.execute(
            "UPDATE subscribers SET tier=?, expires_at=?, active=1, payment_tx=? WHERE telegram_id=?",
            (tier, new_expiry, payment_tx, telegram_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM subscribers WHERE telegram_id=?", (telegram_id,)).fetchone()
        conn.close()
        return Subscriber(**dict(row))

    conn.execute(
        "INSERT INTO subscribers (telegram_id, username, tier, expires_at, created_at, payment_tx) VALUES (?,?,?,?,?,?)",
        (telegram_id, username, tier, _expires_iso(duration_days), _now_iso(), payment_tx),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM subscribers WHERE telegram_id=?", (telegram_id,)).fetchone()
    conn.close()
    return Subscriber(**dict(row))


def get_subscriber(telegram_id: str) -> Optional[Subscriber]:
    """Get subscriber by Telegram ID."""
    init_db()
    conn = _connect()
    row = conn.execute("SELECT * FROM subscribers WHERE telegram_id=?", (telegram_id,)).fetchone()
    conn.close()
    return Subscriber(**dict(row)) if row else None


def is_active(telegram_id: str) -> bool:
    """Check if subscriber has an active paid subscription."""
    sub = get_subscriber(telegram_id)
    if not sub or not sub.active:
        return False
    if sub.tier == "free":
        return True
    now = datetime.now(timezone.utc)
    try:
        expiry = datetime.fromisoformat(sub.expires_at.replace("Z", "+00:00"))
        return now < expiry
    except (ValueError, TypeError):
        return False


def list_active_subscribers(tier: str = None) -> list[Subscriber]:
    """List all currently active subscribers, optionally filtered by tier."""
    init_db()
    conn = _connect()
    if tier:
        rows = conn.execute(
            "SELECT * FROM subscribers WHERE active=1 AND tier=? ORDER BY created_at DESC", (tier,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM subscribers WHERE active=1 ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    subs = [Subscriber(**dict(r)) for r in rows]
    now = datetime.now(timezone.utc)
    active = []
    for s in subs:
        if s.tier == "free":
            active.append(s)
            continue
        try:
            expiry = datetime.fromisoformat(s.expires_at.replace("Z", "+00:00"))
            if now < expiry:
                active.append(s)
        except (ValueError, TypeError):
            pass
    return active


def deactivate_expired():
    """Deactivate subscribers whose paid subscription has expired."""
    init_db()
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM subscribers WHERE active=1 AND tier != 'free'"
    ).fetchall()
    now = datetime.now(timezone.utc)
    count = 0
    for r in rows:
        try:
            expiry = datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00"))
            if now >= expiry:
                conn.execute("UPDATE subscribers SET active=0 WHERE id=?", (r["id"],))
                count += 1
        except (ValueError, TypeError):
            pass
    conn.commit()
    conn.close()
    return count


def record_payment(tx_hash: str, from_address: str, amount_usdc: float, tier: str = "pro"):
    """Record a crypto payment. Returns True if new payment processed."""
    init_db()
    conn = _connect()
    existing = conn.execute("SELECT * FROM payments WHERE tx_hash=?", (tx_hash,)).fetchone()
    if existing:
        conn.close()
        return False
    conn.execute(
        "INSERT INTO payments (tx_hash, from_address, amount_usdc, tier, created_at) VALUES (?,?,?,?,?)",
        (tx_hash, from_address, amount_usdc, tier, _now_iso()),
    )
    conn.commit()
    conn.close()
    return True


def get_subscriber_count() -> dict:
    """Get subscriber counts by tier."""
    init_db()
    conn = _connect()
    counts = {}
    for tier in ["free", "pro", "inst"]:
        row = conn.execute(
            "SELECT COUNT(*) as n FROM subscribers WHERE active=1 AND tier=?", (tier,)
        ).fetchone()
        counts[tier] = row["n"] if row else 0
    conn.close()
    return counts
