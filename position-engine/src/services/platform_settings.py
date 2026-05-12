"""PlatformSettingsService — thin wrapper over PlatformSettingsRepository."""
from __future__ import annotations

from src.db.models import PlatformSettings
from src.db.repositories import PlatformSettingsRepository
from src.logging_config import get_logger

log = get_logger(__name__)

_repo = PlatformSettingsRepository()  # singleton with in-process cache


async def get_platform_settings() -> PlatformSettings:
    """Fetch (possibly cached) platform settings."""
    return await _repo.get()


async def require_global_trading_enabled() -> PlatformSettings:
    """Fetch settings and raise if global_trading_enabled=False."""
    ps = await _repo.get()
    if not ps.global_trading_enabled:
        raise RuntimeError("Global trading kill switch is active — trading halted")
    return ps
