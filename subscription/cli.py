#!/usr/bin/env python3
"""Subscription Admin CLI.

Usage:
    python -m subscription.cli list                  # List all subscribers
    python -m subscription.cli add <telegram_id> <tier>  # Manually add subscriber
    python -m subscription.cli remove <telegram_id>     # Deactivate subscriber
    python -m subscription.cli status                   # Subscriber stats
    python -m subscription.cli cleanup                  # Deactivate expired
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from subscription.engine import (
    add_subscriber, list_active_subscribers, deactivate_expired,
    get_subscriber, get_subscriber_count, init_db,
)


def cmd_list():
    subs = list_active_subscribers()
    if not subs:
        print("No active subscribers.")
        return
    print(f"{'ID':<20} {'Tier':<8} {'Expires':<12} {'Active':<8}")
    print("-" * 50)
    for s in subs:
        print(f"{s.telegram_id:<20} {s.tier:<8} {s.expires_at[:10]:<12} {'YES' if s.active else 'NO':<8}")


def cmd_add(telegram_id: str, tier: str = "pro", days: int = 30):
    if tier not in ("free", "pro", "inst"):
        print(f"Invalid tier: {tier}. Use free/pro/inst.")
        return
    sub = add_subscriber(telegram_id, username=telegram_id, tier=tier, duration_days=days)
    print(f"Subscriber added: {sub.telegram_id} | tier={sub.tier} | expires={sub.expires_at[:10]}")


def cmd_remove(telegram_id: str):
    sub = get_subscriber(telegram_id)
    if not sub:
        print(f"Subscriber {telegram_id} not found.")
        return
    add_subscriber(telegram_id, tier="free", duration_days=0)
    print(f"Subscriber {telegram_id} downgraded to free.")


def cmd_status():
    counts = get_subscriber_count()
    print("Active Subscribers:")
    print(f"  Free:  {counts.get('free', 0)}")
    print(f"  Pro:   {counts.get('pro', 0)} (${counts.get('pro', 0) * 49}/mo)")
    print(f"  Inst:  {counts.get('inst', 0)} (${counts.get('inst', 0) * 199}/mo)")
    total_mrr = counts.get("pro", 0) * 49 + counts.get("inst", 0) * 199
    print(f"  MRR:   ${total_mrr}")


def cmd_cleanup():
    count = deactivate_expired()
    print(f"Deactivated {count} expired subscriber(s).")


def main():
    init_db()
    if len(sys.argv) < 2:
        print("Usage: python -m subscription.cli <list|add|remove|status|cleanup>")
        return

    cmd = sys.argv[1]
    if cmd == "list":
        cmd_list()
    elif cmd == "add" and len(sys.argv) >= 3:
        tier = sys.argv[3] if len(sys.argv) >= 4 else "pro"
        cmd_add(sys.argv[2], tier)
    elif cmd == "remove" and len(sys.argv) >= 3:
        cmd_remove(sys.argv[2])
    elif cmd == "status":
        cmd_status()
    elif cmd == "cleanup":
        cmd_cleanup()
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
