import { Badge, type BadgeProps } from "../primitives/badge";

type LifecycleStatus =
  | "idle"
  | "monitoring"
  | "closing"
  | "closed"
  | "failed"
  | "needs_reconciliation";

type TradeMode = "paper" | "live" | "shadow";
type TradeStatus = "open" | "closed" | "cancelled" | "failed" | "simulated" | "pending";
type ApprovalStatus = "approved" | "auto_approved" | "pending" | "rejected" | "manual_review";

const LIFECYCLE_VARIANT: Record<LifecycleStatus, BadgeProps["variant"]> = {
  idle:                 "secondary",
  monitoring:           "default",
  closing:              "warning",
  closed:               "outline",
  failed:               "destructive",
  needs_reconciliation: "destructive",
};

const MODE_VARIANT: Record<TradeMode, BadgeProps["variant"]> = {
  paper:  "secondary",
  shadow: "outline",
  live:   "destructive",
};

const STATUS_VARIANT: Record<TradeStatus, BadgeProps["variant"]> = {
  open:      "default",
  closed:    "outline",
  cancelled: "secondary",
  failed:    "destructive",
  simulated: "secondary",
  pending:   "warning",
};

const APPROVAL_VARIANT: Record<ApprovalStatus, BadgeProps["variant"]> = {
  approved:        "success",
  auto_approved:   "success",
  pending:         "warning",
  rejected:        "destructive",
  manual_review:   "warning",
};

export function LifecycleBadge({ status }: { status: string }) {
  const variant = LIFECYCLE_VARIANT[status as LifecycleStatus] ?? "outline";
  return <Badge variant={variant}>{status}</Badge>;
}

export function ModeBadge({ mode }: { mode: string }) {
  const variant = MODE_VARIANT[mode as TradeMode] ?? "outline";
  return <Badge variant={variant}>{mode}</Badge>;
}

export function StatusBadge({ status }: { status: string }) {
  const variant = STATUS_VARIANT[status as TradeStatus] ?? "outline";
  return <Badge variant={variant}>{status}</Badge>;
}

export function ApprovalBadge({ status }: { status: string }) {
  const variant = APPROVAL_VARIANT[status as ApprovalStatus] ?? "outline";
  return <Badge variant={variant}>{status.replace(/_/g, " ")}</Badge>;
}
