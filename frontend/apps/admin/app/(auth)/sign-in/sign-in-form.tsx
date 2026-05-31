"use client";

import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@ta/ui";

import { supabase } from "@/lib/supabase/client";

export function AdminSignInForm() {
  const searchParams = useSearchParams();
  const next = safeNext(searchParams.get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(searchParams.get("error"));

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { error: authError } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (authError) {
        setError(authError.message);
        setBusy(false);
        return;
      }
      window.location.assign(next);
    } catch (err) {
      setBusy(false);
      setError(err instanceof Error ? err.message : "Could not sign in.");
    }
  }

  return (
    <Card className="w-full max-w-sm border-border/70 bg-card/85 backdrop-blur-xl">
      <CardHeader>
        <CardTitle>Admin access</CardTitle>
        <CardDescription>
          Sign in with an account whose profile role is admin, security_admin, or super_admin.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={onSubmit}>
          <div className="space-y-1.5">
            <Label htmlFor="admin-email">Email</Label>
            <Input
              id="admin-email"
              autoComplete="email"
              disabled={busy}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              value={email}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="admin-password">Password</Label>
            <Input
              id="admin-password"
              autoComplete="current-password"
              disabled={busy}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              value={password}
            />
          </div>
          {error ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error === "{}" ? "Sign in failed. Please try again." : error}
            </div>
          ) : null}
          <Button className="w-full" disabled={busy} type="submit">
            {busy ? "Signing in..." : "Sign in"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function safeNext(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/overview";
  return value;
}
