"""
Exchange adapter factory for the Position Engine.

Paper/shadow mode always uses MockExchangeAdapter.
Live mode uses BinanceExchangeAdapter only when explicitly enabled.
"""
from __future__ import annotations

from src.exchanges.base import ExchangeAdapter
from src.exchanges.mock import MockExchangeAdapter
from src.logging_config import get_logger

log = get_logger(__name__)

_SUPPORTED_LIVE_EXCHANGES = frozenset({"binance"})


def get_paper_adapter(simulated_price: float = 50_000.0) -> ExchangeAdapter:
    """Always returns MockExchangeAdapter. Never calls real exchange."""
    return MockExchangeAdapter(simulated_price=simulated_price)


def get_live_adapter(
    exchange: str,
    api_key: str,
    api_secret: str,
) -> ExchangeAdapter:
    """
    Returns a real exchange adapter for live lifecycle operations.

    NEVER log api_key or api_secret.
    Caller must zero credentials after use.
    """
    exchange_lower = exchange.lower()

    if exchange_lower not in _SUPPORTED_LIVE_EXCHANGES:
        raise ValueError(
            f"Exchange '{exchange}' not supported for live lifecycle. "
            f"Supported: {sorted(_SUPPORTED_LIVE_EXCHANGES)}"
        )

    log.info(
        "exchange_factory.creating_live_adapter",
        exchange=exchange_lower,
        # DO NOT log api_key or api_secret
    )

    if exchange_lower == "binance":
        from src.exchanges.binance import BinanceExchangeAdapter
        return BinanceExchangeAdapter(
            api_key=api_key,
            api_secret=api_secret,
            testnet=False,
        )

    raise ValueError(f"No adapter implemented for exchange: {exchange}")
