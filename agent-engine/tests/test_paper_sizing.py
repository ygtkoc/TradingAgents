from src.db.models import Bot
from src.main import _risk_profile


def test_futures_paper_profile_allows_full_notional_for_risk_sizing():
    bot = Bot(
        id="bot-1",
        user_id="user-1",
        name="Futures Paper Bot",
        max_position_size_pct=5.0,
        metadata={"trading_system": "futures_trading"},
    )

    profile = _risk_profile({"metadata": {"trading_system": "futures_trading"}}, bot)

    assert profile["max_position_pct"] == 100.0


def test_portfolio_profile_uses_wallet_risk_not_position_cap():
    bot = Bot(
        id="bot-1",
        user_id="user-1",
        name="Portfolio Bot",
        max_position_size_pct=5.0,
        metadata={"trading_system": "portfolio_management"},
    )

    profile = _risk_profile({"metadata": {"trading_system": "portfolio_management"}}, bot)

    assert profile["max_position_pct"] == 100.0
