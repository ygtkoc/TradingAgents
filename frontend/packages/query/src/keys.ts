/**
 * Centralised React Query keys.
 *
 * Always use these helpers — never inline string arrays. Centralisation
 * makes invalidation safe (one place to grep for affected queries) and
 * keeps cache hits stable across components.
 */

export const queryKeys = {
  auth: {
    user: () => ["auth", "user"] as const,
  },

  bots: {
    all:    () => ["bots"] as const,
    list:   (userId?: string) => ["bots", "list", { userId }] as const,
    detail: (botId: string) => ["bots", "detail", botId] as const,
    config: (botId: string) => ["bots", "config", botId] as const,
  },

  trades: {
    all:    () => ["trades"] as const,
    list:   (filters: Record<string, unknown> = {}) => ["trades", "list", filters] as const,
    open:   (userId?: string) => ["trades", "open", { userId }] as const,
    detail: (tradeId: string) => ["trades", "detail", tradeId] as const,
    events: (tradeId: string) => ["trades", "events", tradeId] as const,
  },

  decisions: {
    all:               () => ["decisions"] as const,
    list:              (filters: Record<string, unknown> = {}) => ["decisions", "list", filters] as const,
    pendingApproval:   (userId?: string) => ["decisions", "pending-approval", { userId }] as const,
    detail:            (id: string) => ["decisions", "detail", id] as const,
  },

  agentRuns: {
    all:    () => ["agent-runs"] as const,
    list:   (filters: Record<string, unknown> = {}) => ["agent-runs", "list", filters] as const,
    detail: (runId: string) => ["agent-runs", "detail", runId] as const,
    outputs:(runId: string) => ["agent-runs", "outputs", runId] as const,
  },

  exchangeAccounts: {
    all:    () => ["exchange-accounts"] as const,
    list:   (userId?: string) => ["exchange-accounts", "list", { userId }] as const,
    detail: (id: string) => ["exchange-accounts", "detail", id] as const,
  },

  userSettings: {
    detail: (userId: string) => ["user-settings", userId] as const,
  },

  notifications: {
    list:   (userId?: string) => ["notifications", "list", { userId }] as const,
    unread: (userId?: string) => ["notifications", "unread-count", { userId }] as const,
  },

  telegram: {
    accounts: (userId?: string) => ["telegram", "accounts", { userId }] as const,
    chats:    (userId?: string, accountId?: string) => ["telegram", "chats", { userId, accountId }] as const,
    sources:  (userId?: string) => ["telegram", "sources", { userId }] as const,
    messages: (userId?: string) => ["telegram", "messages", { userId }] as const,
  },

  logs: {
    risk:     (filters: Record<string, unknown> = {}) => ["logs", "risk",     filters] as const,
    security: (filters: Record<string, unknown> = {}) => ["logs", "security", filters] as const,
    audit:    (filters: Record<string, unknown> = {}) => ["logs", "audit",    filters] as const,
  },

  admin: {
    overview:         () => ["admin", "overview"] as const,
    users:            (filters: Record<string, unknown> = {}) => ["admin", "users", filters] as const,
    user:             (userId: string) => ["admin", "user", userId] as const,
    reconciliation:   () => ["admin", "reconciliation"] as const,
    platformSettings: () => ["admin", "platform-settings"] as const,
    workers:          () => ["admin", "workers"] as const,
  },
} as const;
