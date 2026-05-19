"""Tests for the cross-platform comparator engine."""
import pytest
from src.data.comparator import similarity, normalize_title, calculate_spread, estimate_profit


def test_normalize_strips_will_prefix():
    assert normalize_title("Will BTC reach $100K in 2026?") == "btc reach $100k in 2026"


def test_normalize_strips_does_prefix():
    assert normalize_title("Does the Fed cut rates tomorrow?") == "the fed cut rates tomorrow"


def test_similarity_exact_match():
    assert similarity("Will BTC hit 100K?", "Will BTC hit 100K?") > 0.95


def test_similarity_close_match():
    score = similarity("Will Bitcoin reach $100,000 in 2026?", "BTC to 100K by end of 2026?")
    assert score > 0.3


def test_similarity_different():
    score = similarity("Will Trump win 2028?", "Will ETH hit $10K?")
    assert score < 0.4


def test_calculate_spread_buy_pm():
    result = calculate_spread(pm_price=0.58, kalshi_price=0.62)
    assert result["direction"] == "buy_pm_sell_kalshi"
    assert result["spread_pct"] == 4.0
    assert result["actionable"] is True


def test_calculate_spread_buy_kalshi():
    result = calculate_spread(pm_price=0.65, kalshi_price=0.60)
    assert result["direction"] == "buy_kalshi_sell_pm"
    assert result["spread_pct"] == 5.0


def test_calculate_spread_below_threshold():
    result = calculate_spread(pm_price=0.505, kalshi_price=0.500)
    assert result["spread_pct"] == 0.5
    assert result["actionable"] is False


def test_calculate_spread_edge_prices():
    result = calculate_spread(pm_price=0.0, kalshi_price=0.5)
    assert result["actionable"] is False


def test_estimate_profit():
    result = estimate_profit(spread_pct=3.0, capital=1000.0)
    assert result["capital"] == 1000.0
    assert result["gross_profit"] == 30.0
    assert result["fees"] == 20.0
    assert result["net_profit"] == 10.0
    assert result["roi_pct"] == 1.0
