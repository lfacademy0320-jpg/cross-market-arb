"""Tests for the settlement check module."""
from src.strategy.settlement_check import check_settlement_risk, flag_high_risk_pairs


def test_government_shutdown_flagged():
    risk = check_settlement_risk(
        market_title="Will the government shutdown happen by June?",
        event_title="US Government Shutdown",
    )
    assert risk.level == "high"
    assert "OPM" in risk.warning


def test_ceasefire_flagged():
    risk = check_settlement_risk(
        market_title="Will a permanent peace deal be signed?",
        event_title="US-Iran Peace Agreement",
    )
    assert risk.level == "high"


def test_crypto_price_low_risk():
    risk = check_settlement_risk(
        market_title="Will BTC be above $300K on Dec 31?",
    )
    assert risk.level == "low"


def test_recession_flagged():
    risk = check_settlement_risk(
        market_title="Will the US enter a recession in 2026?",
    )
    assert risk.level == "medium"


def test_irrelevant_market_low_risk():
    risk = check_settlement_risk(
        market_title="Will it rain in Seattle tomorrow?",
    )
    assert risk.level == "low"
    assert risk.warning == ""
