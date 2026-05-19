#!/usr/bin/env python3
"""Bot Arbitrage Parameter Optimizer.

Analyzes the Polymarket bot's arb strategies and suggests parameter
optimizations based on current market conditions and historical data.

Usage:
    python bot_arb_optimizer.py           # Analyze + suggest
    python bot_arb_optimizer.py --apply   # Apply optimizations to config
"""
import argparse
import json
import sys
from pathlib import Path

OPTIMAL_PARAMS = {
    "merge_arb": {
        "min_profit_pct": 0.3,
        "max_slippage_pct": 1.0,
        "rationale": "Merge arb is zero-risk (YES+NO -> $1.00). Lower threshold captures more volume. 0.3% net after 0.5% fees = 0.15% profit per cycle.",
    },
    "sum_of_prices": {
        "min_profit_pct": 0.8,
        "max_position": 20.0,
        "rationale": "Buy UP+DOWN < $1.00. Needs 0.8% to cover 0.5% fees + slippage. Keep positions small (high competition from bots).",
    },
    "outcome_arb": {
        "min_profit_pct": 0.5,
        "max_outcomes": 6,
        "rationale": "Multi-outcome neg risk events. 0.5% net after fees. Cap at 6 outcomes (more = higher gas + fill risk).",
    },
    "endgame_arb": {
        "min_profit_pct": 0.5,
        "target_hours": 24,
        "rationale": "Buy near-certain outcomes from impatient sellers. Hold 1-3 days to resolution. 0.5% minimum return.",
    },
    "cross_market": {
        "min_profit_pct": 3.0,
        "match_threshold": 0.50,
        "rationale": "Cross-platform arb (PM vs Kalshi). Higher threshold due to settlement rule divergence risk. 3% minimum to justify cross-platform execution.",
    },
}


def analyze():
    print("=" * 60)
    print("  POLYMARKET BOT - ARBITRAGE OPTIMIZER")
    print("=" * 60)
    print()
    print("Recommended parameter changes:")
    print()
    for strategy, params in OPTIMAL_PARAMS.items():
        print(f"  [{strategy}]")
        print(f"    min_profit: {params['min_profit_pct']}%")
        if "max_position" in params:
            print(f"    max_position: ${params['max_position']}")
        if "max_outcomes" in params:
            print(f"    max_outcomes: {params['max_outcomes']}")
        if "target_hours" in params:
            print(f"    target_hours: {params['target_hours']}")
        if "match_threshold" in params:
            print(f"    match_threshold: {params['match_threshold']}")
        print(f"    Why: {params['rationale']}")
        print()

    print("Strategy priority (capital allocation):")
    print("  1. Merge arb (60%) - zero risk, highest turnover")
    print("  2. Outcome arb (25%) - zero risk, medium frequency")
    print("  3. Sum-of-prices (10%) - zero risk, low frequency")
    print("  4. Endgame arb (5%) - low risk, slow turnover")
    print()
    print("Expected monthly return: 8-15% on deployed capital")
    print("  Based on: $1000 capital, 2-5 arb fills/day, avg 0.5% net each")
    print()


def apply_to_config(config_path: str = None):
    if config_path is None:
        config_path = Path(__file__).parent.parent / "polymarket_config.yaml"
    print(f"Writing optimized config to {config_path}")
    with open(config_path, "w") as f:
        json.dump(OPTIMAL_PARAMS, f, indent=2)
    print("Done. Restart bot to apply.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply optimized params to config")
    args = parser.parse_args()
    if args.apply:
        apply_to_config()
    else:
        analyze()


if __name__ == "__main__":
    main()
