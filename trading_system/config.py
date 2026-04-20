import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    trading_mode: str = os.getenv("TRADING_MODE", "paper")
    risk_per_trade: float = float(os.getenv("RISK_PER_TRADE", "0.02"))
    max_positions: int = int(os.getenv("MAX_POSITIONS", "8"))
    portfolio_cash: float = float(os.getenv("PORTFOLIO_CASH", "100000.00"))
    refresh_interval: int = int(os.getenv("REFRESH_INTERVAL", "900"))

    data_dir: str = os.path.join(os.path.dirname(__file__), "data")
    watchlist_file: str = os.path.join(data_dir, "watchlist.json")
    portfolio_file: str = os.path.join(data_dir, "portfolio.json")

    def validate(self) -> None:
        if not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set. Check your .env file.")


config = Config()
