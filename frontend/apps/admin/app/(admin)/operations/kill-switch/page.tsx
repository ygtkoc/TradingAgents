"use client";

import { useState } from "react";

import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, PageHeader, ProductPage } from "@ta/ui";

export default function KillSwitchPage() {
  const [armed, setArmed] = useState(false);

  return (
    <ProductPage size="xl">
      <PageHeader
        eyebrow="Operations"
        title="Kill switch"
        description="A focused safety surface for global trading controls. Wiring stays explicit and audited."
      />
      <div className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
        <Card className="border-destructive/25 bg-destructive/5">
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle>Emergency trading halt</CardTitle>
                <CardDescription>Two-step UI guard before invoking backend kill-switch functions.</CardDescription>
              </div>
              <Badge variant={armed ? "destructive" : "secondary"}>{armed ? "armed" : "safe"}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button variant={armed ? "destructive" : "outline"} onClick={() => setArmed((value) => !value)}>
              {armed ? "Disarm" : "Arm kill switch"}
            </Button>
            <Button disabled={!armed} variant="destructive" onClick={() => window.alert("Backend kill-switch invocation should be connected to the audited Edge Function in the next hardening pass.")}>
              Confirm emergency halt
            </Button>
          </CardContent>
        </Card>
        <Card className="border-border/70 bg-card/70">
          <CardHeader>
            <CardTitle>Operator checklist</CardTitle>
            <CardDescription>Use before stopping live execution.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <div className="rounded-lg border border-border/50 bg-background/45 p-3">Check open live positions and exchange connectivity.</div>
            <div className="rounded-lg border border-border/50 bg-background/45 p-3">Review reconciliation and lifecycle errors.</div>
            <div className="rounded-lg border border-border/50 bg-background/45 p-3">Notify affected operators before manual intervention.</div>
          </CardContent>
        </Card>
      </div>
    </ProductPage>
  );
}
