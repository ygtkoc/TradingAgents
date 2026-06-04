"use client";

import { Activity, Eye, EyeOff, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";

import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@ta/ui";
import { cn } from "@ta/utils";

import { isDemoMode } from "@/lib/demo";
import { supabase } from "@/lib/supabase/client";

interface Strength {
  score: 0 | 1 | 2 | 3 | 4;       // 0 = empty, 4 = strong
  label: "Empty" | "Too weak" | "Weak" | "Okay" | "Strong";
  hint?: string;
}

function scorePassword(pw: string): Strength {
  if (!pw) return { score: 0, label: "Empty" };
  let score = 0;
  if (pw.length >= 8)       score++;
  if (/[A-Z]/.test(pw))     score++;
  if (/[0-9]/.test(pw))     score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;

  if (pw.length < 8)        return { score: 1, label: "Too weak", hint: "Use at least 8 characters." };
  if (score <= 1)           return { score: 1, label: "Too weak", hint: "Mix in upper case, numbers, and symbols." };
  if (score === 2)          return { score: 2, label: "Weak",     hint: "Add another character class." };
  if (score === 3)          return { score: 3, label: "Okay",     hint: "Could still be stronger." };
  return                          { score: 4, label: "Strong" };
}

function authCallbackUrl() {
  const configured = process.env.NEXT_PUBLIC_CUSTOMER_URL?.trim().replace(/\/$/, "");
  const origin = configured || window.location.origin;
  return `${origin}/auth/callback`;
}

export default function SignUpPage() {
  const router = useRouter();

  const [fullName, setFullName] = useState("");
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm]   = useState("");
  const [show, setShow]         = useState(false);
  const [busy, setBusy]         = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [info, setInfo]         = useState<string | null>(null);

  const strength = useMemo(() => scorePassword(password), [password]);
  const passwordsMatch = !confirm || password === confirm;

  const createAccountRows = async (userId: string) => {
    try {
      await supabase.from("user_settings").insert({
        user_id:                        userId,
        trading_enabled:                true,
        real_trading_enabled:           false,
        real_trading_allowed:           false,
        real_trading_requires_approval: true,
      });
    } catch { /* table or RLS may not exist yet; ignore for scaffold */ }

    try {
      await supabase.from("profiles").insert({
        id:        userId,
        full_name: fullName.trim(),
      });
    } catch { /* profile table optional */ }
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);

    if (!fullName.trim())   { setError("Please enter your full name."); return; }
    if (strength.score < 3) { setError("Please choose a stronger password."); return; }
    if (!passwordsMatch)    { setError("Passwords do not match.");       return; }

    if (isDemoMode) {
      router.push("/dashboard");
      router.refresh();
      return;
    }

    setBusy(true);
    const { data, error: err } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName.trim() },
        // Email confirmation links will redirect through here.
        emailRedirectTo: authCallbackUrl(),
      },
    });
    if (err) {
      setBusy(false);
      setError(err.message || "Could not create account.");
      return;
    }

    // If email-confirmation is enabled, there is no session yet.
    if (data.session && data.user) {
      // Best-effort: create user_settings + profile rows. RLS scopes inserts
      // to the authed user. NOTE: trades/decisions/etc. are still off-limits.
      await createAccountRows(data.user.id);

      setBusy(false);
      router.push("/dashboard");
      router.refresh();
      return;
    }

    // If signup did not return a session, autoconfirm may still allow login.
    const { data: signInData, error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (!signInError && signInData.session && signInData.user) {
      await createAccountRows(signInData.user.id);
      setBusy(false);
      router.push("/dashboard");
      router.refresh();
      return;
    }

    setBusy(false);
    setInfo("Check your inbox to confirm your email. You can close this tab.");
  };

  const showStrength = password.length > 0;
  const segmentColors = ["bg-destructive", "bg-destructive", "bg-warning", "bg-warning", "bg-success"];

  return (
    <div className="space-y-6">
      <header className="space-y-2 text-center lg:hidden">
        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-md bg-primary/15 text-primary">
          <Activity className="h-5 w-5" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">lucrandos</h1>
      </header>

      <Card>
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl">Create your account</CardTitle>
          <CardDescription>Start with paper trading. Live trading stays disabled by default.</CardDescription>
        </CardHeader>

        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit} noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="name">Full name</Label>
              <Input
                id="name"
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                disabled={busy}
                placeholder="Ada Lovelace"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={busy}
                placeholder="you@example.com"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={show ? "text" : "password"}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={busy}
                  className="pr-9"
                />
                <button
                  type="button"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  onClick={() => setShow((s) => !s)}
                  aria-label={show ? "Hide password" : "Show password"}
                  tabIndex={-1}
                >
                  {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>

              {showStrength ? (
                <div className="space-y-1">
                  <div className="flex gap-1">
                    {[0, 1, 2, 3].map((i) => (
                      <div
                        key={i}
                        className={cn(
                          "h-1 flex-1 rounded-full",
                          i < strength.score
                            ? segmentColors[Math.min(strength.score, 4) - 1]
                            : "bg-muted",
                        )}
                      />
                    ))}
                  </div>
                  <div className="flex justify-between text-[11px]">
                    <span className="text-muted-foreground">{strength.label}</span>
                    {strength.hint ? (
                      <span className="text-muted-foreground">{strength.hint}</span>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="confirm">Confirm password</Label>
              <Input
                id="confirm"
                type={show ? "text" : "password"}
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                disabled={busy}
                aria-invalid={!passwordsMatch}
              />
              {!passwordsMatch ? (
                <p className="text-xs text-destructive">Passwords do not match.</p>
              ) : null}
            </div>

            {error ? (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive-foreground">
                {error}
              </div>
            ) : null}
            {info ? (
              <div className="rounded-md border border-success/40 bg-success/10 px-3 py-2 text-xs">
                {info}
              </div>
            ) : null}

            <Button
              type="submit"
              className="w-full"
              disabled={busy || strength.score < 3 || !passwordsMatch}
            >
              {busy ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating account…
                </>
              ) : isDemoMode ? (
                "Continue to demo"
              ) : (
                "Create account"
              )}
            </Button>

            <p className="text-center text-[11px] text-muted-foreground">
              By creating an account you agree to our{" "}
              <Link href="/legal/terms" className="underline underline-offset-4">terms</Link>{" "}
              and{" "}
              <Link href="/legal/privacy" className="underline underline-offset-4">privacy policy</Link>.
            </p>
          </form>
        </CardContent>
      </Card>

      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/sign-in" className="font-medium text-foreground underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
