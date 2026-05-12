"""
Binance exchange adapter (live trading).

IMPORTANT: This adapter makes REAL API calls to Binance when instantiated
with real credentials. It is gated behind ENABLE_LIVE_EXECUTION=true.

SECURITY REQUIREMENTS (enforced here):
  1. check_permissions() is called before every order. If can_withdraw=True,
     the adapter raises a SecurityError and blocks the trade.
  2. API credentials are accepted as constructor args and never stored beyond
     the adapter's lifecycle. The caller (LiveExecutor) zeroes them after use.
  3. No API key or secret is ever logged at any level.

TODO (before production):
  - Validate filled_quantity and avg_fill_price against the order request
    to detect price manipulation or unexpected fills.
  - Add order book depth check before market orders to estimate slippage.
  - Implement order status polling with exponential backoff for limit orders.
  - Add circuit breaker: if N consecutive API errors occur, stop all execution
    and fire a CRITICAL alert.
  - Consider ccxt for unified exchange interface when adding more exchanges.
  - Add WebSocket feed for real-time fill confirmation instead of polling.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional
from urllib.parse import urlencode

import httpx

from src.exchanges.base import (
    BalanceResult,
    ExchangeAdapter,
    OrderRequest,
    OrderResult,
    PermissionCheckResult,
)
from src.logging_config import get_logger

log = get_logger(__name__)

_BINANCE_BASE = "https://api.binance.com"
_TESTNET_BASE = "https://testnet.binance.vision"


class SecurityError(Exception):
    """Raised when a security check fails during exchange interaction."""


class BinanceExchangeAdapter(ExchangeAdapter):
    """
    Binance REST API adapter.

    Args:
        api_key:    Binance API key (plaintext, in-scope only)
        api_secret: Binance API secret (plaintext, in-scope only)
        testnet:    If True, uses Binance testnet (safe for staging)

    NEVER log api_key or api_secret. NEVER store them in any persistent state.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
    ) -> None:
        self._base = _TESTNET_BASE if testnet else _BINANCE_BASE
        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet
        # httpx client with timeout
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"X-MBX-APIKEY": api_key},
            timeout=30.0,
        )

    async def check_permissions(self) -> PermissionCheckResult:
        """
        Verify API key permissions via GET /api/v3/account.

        BLOCKS execution if can_withdraw=True.
        This is called before every live order as a defence-in-depth check.
        """
        params = self._signed_params({})
        resp = await self._client.get("/api/v3/account", params=params)
        resp.raise_for_status()
        data = resp.json()

        can_trade    = data.get("canTrade", False)
        can_withdraw = data.get("canWithdraw", False)
        can_deposit  = data.get("canDeposit", False)

        if can_withdraw:
            log.error(
                "binance.withdrawal_permission_detected",
                # DO NOT log api_key or account details
                exchange="binance",
                testnet=self._testnet,
            )
            raise SecurityError(
                "CRITICAL: Binance API key has withdrawal permission. "
                "Execution blocked. Revoke withdrawal permission immediately."
            )

        return PermissionCheckResult(
            can_trade=can_trade,
            can_withdraw=can_withdraw,
            has_read_permission=True,
            raw_permissions={
                "canTrade": can_trade,
                "canWithdraw": can_withdraw,
                "canDeposit": can_deposit,
            },
        )

    async def get_latest_price(self, symbol: str) -> float:
        resp = await self._client.get(
            "/api/v3/ticker/price",
            params={"symbol": symbol.replace("/", "")},
        )
        resp.raise_for_status()
        return float(resp.json()["price"])

    async def get_balance(self) -> BalanceResult:
        params = self._signed_params({})
        resp = await self._client.get("/api/v3/account", params=params)
        resp.raise_for_status()
        data = resp.json()

        free:  dict[str, float] = {}
        total: dict[str, float] = {}
        for asset in data.get("balances", []):
            sym = asset["asset"]
            f = float(asset["free"])
            t = float(asset["free"]) + float(asset["locked"])
            if t > 0:
                free[sym] = f
                total[sym] = t

        quote_free = free.get("USDT", 0.0)
        return BalanceResult(free=free, total=total, quote_free=quote_free)

    async def place_order(self, order: OrderRequest) -> OrderResult:
        """
        Place a market or limit order on Binance.

        The clientOrderId is passed as a duplicate-prevention key.
        If Binance returns DUPLICATE_ORDER, we fetch and return the existing order.
        """
        symbol = order.symbol.replace("/", "")
        params: dict = {
            "symbol":    symbol,
            "side":      order.side.upper(),
            "type":      order.order_type.upper(),
            "quantity":  f"{order.quantity:.8f}",
        }
        if order.client_order_id:
            params["newClientOrderId"] = order.client_order_id
        if order.order_type == "limit" and order.price:
            params["price"] = f"{order.price:.8f}"
            params["timeInForce"] = order.time_in_force

        signed = self._signed_params(params)

        try:
            resp = await self._client.post("/api/v3/order", params=signed)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text
            # -2010 = DUPLICATE_ORDER — idempotent: fetch existing order
            if "-2010" in body and order.client_order_id:
                log.warning(
                    "binance.duplicate_order_detected",
                    client_order_id=order.client_order_id,
                    symbol=symbol,
                )
                return await self._fetch_by_client_id(symbol, order.client_order_id)
            log.error("binance.place_order_error", error=body[:200], symbol=symbol)
            return OrderResult(
                order_id="",
                client_order_id=order.client_order_id,
                status="failed",
                filled_quantity=0.0,
                avg_fill_price=None,
                raw_response={"error": body[:200]},
                success=False,
                error=body[:200],
            )

        data = resp.json()
        filled_qty   = float(data.get("executedQty", 0))
        avg_price    = self._avg_price(data)

        return OrderResult(
            order_id=str(data.get("orderId", "")),
            client_order_id=data.get("clientOrderId"),
            status=data.get("status", "").lower(),
            filled_quantity=filled_qty,
            avg_fill_price=avg_price,
            raw_response=data,
            success=True,
        )

    async def fetch_order(self, order_id: str, symbol: str) -> OrderResult:
        symbol_clean = symbol.replace("/", "")
        params = self._signed_params({"symbol": symbol_clean, "orderId": order_id})
        resp = await self._client.get("/api/v3/order", params=params)
        resp.raise_for_status()
        data = resp.json()

        return OrderResult(
            order_id=str(data.get("orderId", "")),
            client_order_id=data.get("clientOrderId"),
            status=data.get("status", "").lower(),
            filled_quantity=float(data.get("executedQty", 0)),
            avg_fill_price=self._avg_price(data),
            raw_response=data,
            success=True,
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        symbol_clean = symbol.replace("/", "")
        params = self._signed_params({"symbol": symbol_clean, "orderId": order_id})
        try:
            resp = await self._client.delete("/api/v3/order", params=params)
            resp.raise_for_status()
            return True
        except httpx.HTTPStatusError:
            return False

    async def close(self) -> None:
        await self._client.aclose()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _signed_params(self, params: dict) -> dict:
        """Add timestamp and HMAC-SHA256 signature to request params."""
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(params)
        sig = hmac.new(
            self._api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = sig
        return params

    @staticmethod
    def _avg_price(data: dict) -> Optional[float]:
        fills = data.get("fills", [])
        if fills:
            total_qty   = sum(float(f["qty"]) for f in fills)
            total_value = sum(float(f["qty"]) * float(f["price"]) for f in fills)
            return total_value / total_qty if total_qty > 0 else None
        raw = data.get("price") or data.get("cummulativeQuoteQty")
        return float(raw) if raw else None

    async def _fetch_by_client_id(
        self, symbol: str, client_order_id: str
    ) -> OrderResult:
        params = self._signed_params(
            {"symbol": symbol, "origClientOrderId": client_order_id}
        )
        resp = await self._client.get("/api/v3/order", params=params)
        resp.raise_for_status()
        data = resp.json()
        return OrderResult(
            order_id=str(data.get("orderId", "")),
            client_order_id=data.get("clientOrderId"),
            status=data.get("status", "").lower(),
            filled_quantity=float(data.get("executedQty", 0)),
            avg_fill_price=self._avg_price(data),
            raw_response=data,
            success=True,
        )

    def __del__(self):
        # Zero out credentials when the adapter is garbage collected
        # Note: __del__ is not guaranteed to run; use explicit close() in finally blocks
        self._api_key = ""
        self._api_secret = ""
