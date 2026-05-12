import type { Notification } from "@ta/types";

const HOUR = 60 * 60 * 1000;

export const demoNotifications: Notification[] = [
  {
    id:    "demo-notif-001",
    user_id: "demo-user-00000000-0000-0000-0000-000000000001",
    type:  "trade_executed",
    title: "Trade executed: BTC/USDT long",
    body:  "BTC Momentum opened a long at 60,124.30. Take-profit set at 63,130.51.",
    read:  false,
    metadata: {},
    created_at: new Date(Date.now() - 1 * HOUR).toISOString(),
  },
  {
    id:    "demo-notif-002",
    user_id: "demo-user-00000000-0000-0000-0000-000000000001",
    type:  "decision_pending_approval",
    title: "Manual approval required",
    body:  "ETH Mean Reversion is awaiting your approval for an open_long decision.",
    read:  false,
    metadata: {},
    created_at: new Date(Date.now() - 3 * HOUR).toISOString(),
  },
  {
    id:    "demo-notif-003",
    user_id: "demo-user-00000000-0000-0000-0000-000000000001",
    type:  "reconciliation_required",
    title: "Reconciliation required: SOL/USDT",
    body:  "An open SOL trade reported a partial fill. Operator review needed.",
    read:  false,
    metadata: {},
    created_at: new Date(Date.now() - 6 * HOUR).toISOString(),
  },
  {
    id:    "demo-notif-004",
    user_id: "demo-user-00000000-0000-0000-0000-000000000001",
    type:  "trade_closed",
    title: "Trade closed: ETH/USDT take_profit",
    body:  "ETH/USDT short closed at take-profit. Realised P&L +84.20 USDT.",
    read:  true,
    metadata: {},
    created_at: new Date(Date.now() - 24 * HOUR).toISOString(),
  },
];
