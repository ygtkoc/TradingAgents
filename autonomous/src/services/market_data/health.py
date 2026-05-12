"""
Helpers to query feed liveness from outside the feed module.

Stale-feed detection runs against the *cache* (in-memory) rather than the DB
because the DB is a downstream sink. If the cache hasn't seen any update in
`market_data_stale_after_seconds`, the signal generator must pause.
"""
from __future__ import annotations

from typing import Optional

from src.config import settings
from src.services.market_data.cache import MarketDataCache


def last_seen_age_seconds(cache: MarketDataCache) -> Optional[float]:
    return cache.global_age_seconds()


def is_feed_stale(cache: MarketDataCache) -> bool:
    age = cache.global_age_seconds()
    if age is None:
        return True  # never seen anything
    return age > settings.market_data_stale_after_seconds
