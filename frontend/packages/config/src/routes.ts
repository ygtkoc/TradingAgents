/**
 * Centralised route name constants. Use these instead of string literals
 * so renames are safe and analytics/breadcrumbs can map paths to labels.
 */

export const customerRoutes = {
  // Public auth flows
  signIn:        "/sign-in",
  signUp:        "/sign-up",
  resetPassword: "/reset-password",
  verifyEmail:   "/verify-email",
  authCallback:  "/auth/callback",

  // App shell
  dashboard:     "/dashboard",

  bots:          "/bots",
  newBot:        "/bots/new",
  bot:           (botId: string) => `/bots/${botId}`,
  botConfig:     (botId: string) => `/bots/${botId}/config`,
  botTrades:     (botId: string) => `/bots/${botId}/trades`,
  botDecisions:  (botId: string) => `/bots/${botId}/decisions`,
  botAgentRuns:  (botId: string) => `/bots/${botId}/agent-runs`,
  botLogs:       (botId: string) => `/bots/${botId}/logs`,

  trades:        "/trades",
  openTrades:    "/trades/open",
  tradeHistory:  "/trades/history",
  trade:         (tradeId: string) => `/trades/${tradeId}`,

  decisions:     "/decisions",
  pendingApproval: "/decisions/pending-approval",
  decision:      (decisionId: string) => `/decisions/${decisionId}`,

  exchangeAccounts:    "/exchange-accounts",
  newExchangeAccount:  "/exchange-accounts/new",
  exchangeAccount:     (id: string) => `/exchange-accounts/${id}`,

  notifications: "/notifications",

  settings:        "/settings",
  profile:         "/settings/profile",
  securitySettings:"/settings/security",
  tradingSettings: "/settings/trading",
  billing:         "/settings/billing",

  help: "/help",
} as const;

export const adminRoutes = {
  signIn:        "/sign-in",
  authCallback:  "/auth/callback",

  overview:      "/overview",

  users:         "/users",
  user:          (userId: string) => `/users/${userId}`,

  bots:          "/bots",
  trades:        "/trades",
  decisions:     "/decisions",
  agentRuns:     "/agent-runs",

  securityLogs:  "/logs/security",
  riskLogs:      "/logs/risk",
  auditLogs:     "/logs/audit",

  reconciliation: "/reconciliation",
  reconciliationDetail: (tradeId: string) => `/reconciliation/${tradeId}`,

  platformSettings: "/system/platform-settings",
  workers:          "/system/workers",
  featureFlags:     "/system/feature-flags",
  exchanges:        "/system/exchanges",

  killSwitch:    "/operations/kill-switch",
  broadcast:     "/operations/broadcast",
} as const;

export const marketingRoutes = {
  home:     "/",
  pricing:  "/pricing",
  features: "/features",
  blog:     "/blog",
  blogPost: (slug: string) => `/blog/${slug}`,
  docs:     "/docs",
  contact:  "/contact",
  terms:    "/legal/terms",
  privacy:  "/legal/privacy",
} as const;
