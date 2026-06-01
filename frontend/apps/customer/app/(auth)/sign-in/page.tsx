"use client";

import { Activity, Eye, EyeOff, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Button, Input, Label } from "@ta/ui";

import { isDemoMode } from "@/lib/demo";
import { supabase }   from "@/lib/supabase/client";

function SignInForm() {
  const router       = useRouter();
  const searchParams = useSearchParams();
  const requestedNext = searchParams.get("next");
  const callbackError = searchParams.get("error");
  const next          = requestedNext?.startsWith("/") && !requestedNext.startsWith("//")
    ? requestedNext
    : "/dashboard";

  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow]         = useState(false);
  const [busy, setBusy]         = useState(false);
  const [error, setError]       = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (isDemoMode) {
      window.location.assign(next);
      return;
    }

    setBusy(true);
    try {
      const { error: err } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      setBusy(false);

      if (err) {
        setError(formatAuthError(err));
        return;
      }
      window.location.assign(next);
    } catch (err) {
      setBusy(false);
      setError(formatAuthError(err));
    }
  };

  const visibleError = error ?? formatCallbackError(callbackError);

  return (
    <div className="space-y-6">
      {/* Brand mark (mobile only) */}
      <header className="flex flex-col items-center gap-2 lg:hidden">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 ring-1 ring-primary/20">
          <Activity className="h-5 w-5 text-primary" />
        </div>
        <span className="text-lg font-bold tracking-tight">lucrandos</span>
      </header>

      {/* Sign-in card */}
      <div className="overflow-hidden rounded-2xl border border-border/60 bg-card/80 shadow-[0_4px_32px_rgba(0,0,0,0.5)] backdrop-blur-xl">
        <div className="p-7">
          <div className="mb-6">
            <h1 className="text-[20px] font-bold tracking-tight text-foreground">Welcome back</h1>
            <p className="mt-1 text-[13px] text-muted-foreground">
              Sign in to your lucrandos dashboard.
            </p>
          </div>

          <form className="space-y-4" onSubmit={onSubmit} noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-[12px] font-semibold text-muted-foreground">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={busy}
                className="h-10 rounded-xl border-border/60 bg-card/60 text-[13px] placeholder:text-muted-foreground/40"
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className="text-[12px] font-semibold text-muted-foreground">
                  Password
                </Label>
                <Link
                  href="/reset-password"
                  className="text-[11px] text-muted-foreground/60 underline-offset-4 hover:text-foreground hover:underline"
                >
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <Input
                  id="password"
                  type={show ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={busy}
                  className="h-10 rounded-xl border-border/60 bg-card/60 pr-9 text-[13px]"
                />
                <button
                  type="button"
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-foreground"
                  onClick={() => setShow((s) => !s)}
                  aria-label={show ? "Hide password" : "Show password"}
                  tabIndex={-1}
                >
                  {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {visibleError ? (
              <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-[12px] text-destructive">
                {visibleError}
              </div>
            ) : null}

            <Button type="submit" className="h-10 w-full rounded-xl text-[13px]" disabled={busy}>
              {busy ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Signing in…</>
              ) : isDemoMode ? "Continue to demo" : "Sign in"}
            </Button>

            {isDemoMode ? (
              <p className="text-center text-[12px] text-muted-foreground/60">
                Demo mode — any credentials pass through.
              </p>
            ) : null}
          </form>
        </div>

        {/* Footer */}
        <div className="border-t border-border/30 bg-card/40 px-7 py-4">
          <p className="text-center text-[12px] text-muted-foreground/60">
            Don&apos;t have an account?{" "}
            <Link href="/sign-up" className="font-semibold text-foreground underline-offset-4 hover:underline">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={<div className="surface-panel h-96 rounded-lg" />}>
      <SignInForm />
    </Suspense>
  );
}

function formatCallbackError(value: string | null) {
  if (!value) return null;
  try {
    const decoded = decodeURIComponent(value);
    if (decoded === "auth_timeout") {
      return "Authentication check timed out. Please sign in again.";
    }
    return decoded === "{}" ? "Sign in failed. Please try again." : decoded;
  } catch {
    return "Sign in failed. Please try again.";
  }
}

function formatAuthError(error: unknown) {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  if (typeof error === "object" && error !== null) {
    const maybeMessage = (error as { message?: unknown; error_description?: unknown }).message
      ?? (error as { message?: unknown; error_description?: unknown }).error_description;
    if (typeof maybeMessage === "string" && maybeMessage.trim()) {
      return maybeMessage;
    }
  }

  if (typeof error === "string" && error.trim() && error !== "{}") {
    return error;
  }

  return "Could not sign in. Check your credentials and try again.";
}
