"""
Exchange adapter factory.

Returns the appropriate adapter based on exchange name and execution mode.
Paper and shadow modes always use MockExchangeAdapter regardless of exchange.
Live mode uses the real adapter — only if ENABLE_LIVE_EXECUTION=true.
"""
from __future__ import annotations

from src.config import settings
from src.exchanges.base import ExchangeAdapter
from src.exchanges.mock import MockExchangeAdapter
from src.logging_config import get_logger

log = get_logger(__name__)

_SUPPORTED_LIVE_EXCHANGES = frozenset({"binance"})


def get_paper_adapter(current_price: float = 0.0) -> ExchangeAdapter:
    """Always returns MockExchangeAdapter. Never calls real exchange."""
    return MockExchangeAdapter(simulated_price=current_price or 50_000.0)


def get_live_adapter(
    exchange: str,
    api_key: str,
    api_secret: str,
) -> ExchangeAdapter:
    """
    Returns a real exchange adapter for live trading.

    SAFETY: Only call this after:
      1. ENABLE_LIVE_EXECUTION is verified True
      2. All security checks passed
      3. All risk checks passed

    The api_key and api_secret are plaintext — zero them out after use.
    NEVER pass them to any other function or log them.
    """
    exchange_lower = exchange.lower()

    if exchange_lower not in _SUPPORTED_LIVE_EXCHANGES:
        raise ValueError(
            f"Exchange '{exchange}' is not supported for live trading. "
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
            testnet=False,  # TODO: add BINANCE_TESTNET=true env for staging
        )

    # Should never reach here (checked above), but explicit fallthrough = fail closed
    raise ValueError(f"No adapter implemented for exchange: {exchange}")
