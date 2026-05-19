"""Tests for Kalshi API client — uses mock responses."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.data.kalshi import KalshiClient


def _mock_response(json_data: dict, status_code: int = 200):
    """Build a fake httpx Response with sync .json()."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = lambda: None
    return resp


@pytest.fixture
def kalshi():
    return KalshiClient("https://fake.kalshi.com/v2")


@pytest.mark.asyncio
async def test_list_events_empty(kalshi):
    with patch.object(kalshi._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response({"events": []})
        events = await kalshi.list_events()
        assert events == []


@pytest.mark.asyncio
async def test_list_events_with_data(kalshi):
    fake = {"events": [{"ticker": "WILL-BTC-100K-2026", "title": "BTC 100K?", "volume": 50000}]}
    with patch.object(kalshi._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(fake)
        events = await kalshi.list_events()
        assert len(events) == 1
        assert events[0]["ticker"] == "WILL-BTC-100K-2026"


@pytest.mark.asyncio
async def test_get_market(kalshi):
    fake = {"market": {"ticker": "WILL-BTC-100K-2026", "yes_bid": 0.62, "no_bid": 0.40}}
    with patch.object(kalshi._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _mock_response(fake)
        market = await kalshi.get_market("WILL-BTC-100K-2026")
        assert market["yes_bid"] == 0.62
