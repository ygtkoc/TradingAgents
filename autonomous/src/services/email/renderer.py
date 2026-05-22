"""
Email renderer for trade-related notifications.

Renders a single HTML template with values pulled from the Trade row + a
trade_event row. Output is intentionally minimal — fintech-clean, no heavy
imagery, works in plain-text fallback. The dashboard link points at
$EMAIL_DASHBOARD_URL/trades/<id>.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.services.email.provider import EMAIL_DASHBOARD_URL


@dataclass
class RenderedEmail:
    subject: str
    html:    str
    text:    str


_BASE_CSS = """
<style>
  body { background:#0b0f17; color:#e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding:24px; }
  .card { background: linear-gradient(180deg,#111827 0%, #0b0f17 100%); border:1px solid #1f2937; border-radius:12px; padding:24px; max-width:560px; margin:0 auto; }
  h1 { font-size:18px; margin:0 0 4px 0; color:#f8fafc; }
  .sub { color:#94a3b8; font-size:13px; margin:0 0 20px 0; }
  table { width:100%; border-collapse: collapse; font-size:13px; }
  td { padding:8px 0; border-bottom:1px solid #1f2937; }
  td.k { color:#94a3b8; }
  td.v { color:#e2e8f0; text-align:right; font-variant-numeric: tabular-nums; }
  .pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:600; }
  .pill.live { background:#7f1d1d; color:#fef2f2; }
  .pill.paper { background:#1e3a8a; color:#dbeafe; }
  .pill.shadow { background:#374151; color:#e5e7eb; }
  .pnl-pos { color:#22c55e; }
  .pnl-neg { color:#ef4444; }
  .cta { display:inline-block; margin-top:20px; padding:10px 16px; background:#3b82f6; color:#fff !important; border-radius:8px; text-decoration:none; font-weight:600; font-size:13px; }
  .footer { color:#64748b; font-size:11px; margin-top:24px; text-align:center; }
</style>
"""


def _row(label: str, value: str) -> str:
    return f"<tr><td class='k'>{label}</td><td class='v'>{value}</td></tr>"


def _fmt_money(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{n:,.2f}"


def _fmt_qty(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{n:,.6g}"


def render_trade_email(*, trade: dict[str, Any], event_type: str) -> RenderedEmail:
    """
    `event_type` is "trade_opened" | "trade_closed".
    `trade` is a dict matching the public.trades row.
    """
    is_close = event_type == "trade_closed"
    mode     = trade.get("mode") or "paper"
    symbol   = trade.get("symbol") or "?"
    side     = trade.get("side")   or trade.get("direction") or "?"
    pnl      = trade.get("realized_pnl") if is_close else trade.get("unrealized_pnl")
    pnl_class = "pnl-pos" if (pnl or 0) >= 0 else "pnl-neg"
    title    = "Position closed" if is_close else "Position opened"
    pill     = f"<span class='pill {mode}'>{mode.upper()}</span>"

    rows = [
        _row("Symbol",       f"<strong>{symbol}</strong>"),
        _row("Side",         str(side).upper()),
        _row("Mode",         pill),
        _row("Quantity",     _fmt_qty(trade.get("quantity"))),
        _row("Entry price",  _fmt_money(trade.get("entry_price"))),
    ]
    if is_close:
        rows.append(_row("Exit price", _fmt_money(trade.get("exit_price") or trade.get("avg_exit_price"))))
        rows.append(_row("Realised P&amp;L",
                          f"<span class='{pnl_class}'>{_fmt_money(pnl)}</span>"))
        rows.append(_row("Reason",     trade.get("close_reason") or "—"))
    else:
        if trade.get("stop_loss"):
            rows.append(_row("Stop loss",   _fmt_money(trade.get("stop_loss"))))
        if trade.get("take_profit"):
            rows.append(_row("Take profit", _fmt_money(trade.get("take_profit"))))

    rows.append(_row("Created", str(trade.get("created_at") or "")))

    trade_id = trade.get("id") or ""
    cta_url  = f"{EMAIL_DASHBOARD_URL}/trades/{trade_id}"

    html = f"""
{_BASE_CSS}
<div class="card">
  <h1>{title}</h1>
  <p class="sub">{symbol} · {mode.upper()}</p>
  <table>
    {''.join(rows)}
  </table>
  <a class="cta" href="{cta_url}">Open in dashboard</a>
  <p class="footer">lucrandos · automated paper-trading notification</p>
</div>
"""

    text = (
        f"{title} — {symbol} ({mode.upper()})\n"
        f"side={side} qty={_fmt_qty(trade.get('quantity'))} "
        f"entry={_fmt_money(trade.get('entry_price'))}\n"
    )
    if is_close:
        text += (
            f"exit={_fmt_money(trade.get('exit_price') or trade.get('avg_exit_price'))} "
            f"pnl={_fmt_money(pnl)} reason={trade.get('close_reason') or '—'}\n"
        )
    text += f"\nView: {cta_url}\n"

    subject = (
        f"[Paper] {symbol} closed — P&L {_fmt_money(pnl)}"
        if is_close else
        f"[Paper] {symbol} opened — {str(side).upper()} {_fmt_qty(trade.get('quantity'))}"
    )

    return RenderedEmail(subject=subject, html=html, text=text)
