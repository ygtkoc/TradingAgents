"use client";

import {
  Button,
  Card, CardContent, CardDescription, CardHeader, CardTitle,
  EmptyState,
  Input,
  Label,
  PageHeader,
  Switch,
  Tabs, TabsContent, TabsList, TabsTrigger,
} from "@ta/ui";
import { CreditCard, Lock, Settings2, User } from "lucide-react";
import { useEffect, useState } from "react";

import { useCurrentUser } from "@/lib/hooks/queries/use-current-user";
import { useUserSettings } from "@/lib/hooks/queries/use-user-settings";
import { supabase } from "@/lib/supabase/client";

export default function SettingsPage() {
  const { data: user }     = useCurrentUser();
  const settingsQuery      = useUserSettings();
  const { data: settings } = settingsQuery;
  const [walletRiskPct, setWalletRiskPct] = useState("2");
  const [riskStatus, setRiskStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

  useEffect(() => {
    if (settings?.default_risk_per_trade_pct != null) {
      setWalletRiskPct(String(settings.default_risk_per_trade_pct));
    }
  }, [settings?.default_risk_per_trade_pct]);

  const saveWalletRisk = async () => {
    if (!user) return;
    const value = Number(walletRiskPct);
    if (!Number.isFinite(value) || value < 0.1 || value > 10) {
      setRiskStatus("error");
      return;
    }
    setRiskStatus("saving");
    const { error } = await supabase
      .from("user_settings")
      .update({ default_risk_per_trade_pct: value } as never)
      .eq("user_id", user.id);
    if (error) {
      console.error("settings.wallet_risk.update.failed", { error });
      setRiskStatus("error");
      return;
    }
    await settingsQuery.refetch();
    setRiskStatus("saved");
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5">
      <PageHeader
        title="Settings"
        description="Profile, security, trading limits, and billing."
      />

      <Tabs defaultValue="profile">
        <TabsList className="rounded-xl border border-border/40 bg-card/60 p-1">
          {[
            { value: "profile",  label: "Profile",  icon: User },
            { value: "trading",  label: "Trading",  icon: Settings2 },
            { value: "security", label: "Security", icon: Lock },
            { value: "billing",  label: "Billing",  icon: CreditCard },
          ].map(({ value, label, icon: Icon }) => (
            <TabsTrigger
              key={value}
              value={value}
              className="gap-1.5 rounded-lg text-[12px] font-medium data-[state=active]:bg-primary/10 data-[state=active]:text-primary"
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* ── Profile ─────────────────────────────────────────────────────────── */}
        <TabsContent value="profile" className="mt-4">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <User className="h-4 w-4 text-muted-foreground/50" />
                <CardTitle>Profile</CardTitle>
              </div>
              <CardDescription>Your account information.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="email" className="text-[12px] text-muted-foreground/80">Email address</Label>
                  <Input id="email" value={user?.email ?? ""} readOnly
                    className="bg-card/40 text-[13px] font-medium" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="role" className="text-[12px] text-muted-foreground/80">Role</Label>
                  <Input id="role" value={user?.role ?? ""} readOnly
                    className="bg-card/40 text-[13px] font-medium capitalize" />
                </div>
              </div>
              <div className="rounded-xl border border-border/30 bg-card/30 px-4 py-3 text-[12px] text-muted-foreground">
                Profile editing and email changes are handled through Supabase Auth. Full edit UI ships in a follow-up.
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Trading ─────────────────────────────────────────────────────────── */}
        <TabsContent value="trading" className="mt-4">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Settings2 className="h-4 w-4 text-muted-foreground/50" />
                <CardTitle>Trading limits</CardTitle>
              </div>
              <CardDescription>
                Account-wide caps. The Execution Engine enforces these server-side.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Master switch */}
              <div className="flex items-center justify-between rounded-xl border border-border/40 bg-card/40 px-4 py-4">
                <div>
                  <div className="text-[13px] font-medium text-foreground">Trading enabled</div>
                  <div className="mt-0.5 text-[12px] text-muted-foreground">
                    Master switch for your account — disabling halts all execution.
                  </div>
                </div>
                <Switch checked={!!settings?.trading_enabled} disabled />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="wallet-risk" className="text-[12px] text-muted-foreground/80">
                    Wallet risk per trade (%)
                  </Label>
                  <div className="flex gap-2">
                    <Input
                      id="wallet-risk"
                      type="number"
                      value={walletRiskPct}
                      step="0.1"
                      min="0.1"
                      max="10"
                      onChange={(event) => {
                        setWalletRiskPct(event.target.value);
                        setRiskStatus("idle");
                      }}
                      className="bg-card/40 text-[13px] font-medium"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      disabled={riskStatus === "saving"}
                      onClick={() => void saveWalletRisk()}
                    >
                      {riskStatus === "saving" ? "Saving" : "Save"}
                    </Button>
                  </div>
                  <div className="text-[11px] text-muted-foreground">
                    At $1,000 balance, {Number(walletRiskPct || 0).toFixed(2)}% risk equals{" "}
                    ${(1000 * Number(walletRiskPct || 0) / 100).toFixed(2)} 1R.
                  </div>
                  {riskStatus === "saved" ? (
                    <div className="text-[11px] font-medium text-success">Wallet risk saved.</div>
                  ) : riskStatus === "error" ? (
                    <div className="text-[11px] font-medium text-destructive">Enter a value from 0.1 to 10.</div>
                  ) : null}
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="daily-loss" className="text-[12px] text-muted-foreground/80">
                    Daily loss limit (USD)
                  </Label>
                  <Input
                    id="daily-loss"
                    type="number"
                    value={settings?.daily_loss_limit_usd ?? ""}
                    readOnly
                    className="bg-card/40 text-[13px] font-medium"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="max-trades" className="text-[12px] text-muted-foreground/80">
                    Max concurrent trades
                  </Label>
                  <Input
                    id="max-trades"
                    type="number"
                    value={settings?.max_concurrent_trades ?? ""}
                    readOnly
                    className="bg-card/40 text-[13px] font-medium"
                  />
                </div>
              </div>

              <div className="rounded-xl border border-border/30 bg-card/30 px-4 py-3 text-[12px] text-muted-foreground">
                Editing these calls the{" "}
                <code className="rounded bg-card/60 px-1 font-mono text-[11px]">user-settings-update</code>{" "}
                Edge Function. Form UI ships in a follow-up task.
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Security ────────────────────────────────────────────────────────── */}
        <TabsContent value="security" className="mt-4">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Lock className="h-4 w-4 text-muted-foreground/50" />
                <CardTitle>Security</CardTitle>
              </div>
              <CardDescription>Sessions, MFA, and password changes.</CardDescription>
            </CardHeader>
            <CardContent>
              <EmptyState
                title="Coming soon"
                description="Security settings UI — MFA, session management, password change — ships in a follow-up task."
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Billing ─────────────────────────────────────────────────────────── */}
        <TabsContent value="billing" className="mt-4">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <CreditCard className="h-4 w-4 text-muted-foreground/50" />
                <CardTitle>Billing</CardTitle>
              </div>
              <CardDescription>Plan, usage, and invoices.</CardDescription>
            </CardHeader>
            <CardContent>
              <EmptyState
                title="Billing coming soon"
                description="Stripe integration and subscription management ships in a follow-up task."
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
