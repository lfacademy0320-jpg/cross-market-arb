from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ScanSettings(BaseSettings):
    model_config = {"env_prefix": "", "env_file": ".env", "env_file_encoding": "utf-8"}

    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    kalshi_api_url: str = "https://api.elections.kalshi.com/trade-api/v2"

    min_profit_percent: float = Field(default=1.0, ge=0.01, le=50.0)
    min_volume_24h: float = Field(default=500, ge=0)
    max_scan_markets: int = Field(default=100, ge=1, le=500)

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


class SpreadOpportunity(BaseModel):
    event_title: str
    market_title: str
    polymarket_price: float
    kalshi_price: float
    spread_pct: float
    polymarket_volume_24h: float
    kalshi_volume_24h: float
    polymarket_slug: str = ""
    kalshi_ticker: str = ""
    settlement_risk: str = ""
    settlement_risk_level: str = "low"
    direction: str = ""
