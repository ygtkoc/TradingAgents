"use client";

import { useQuery } from "@tanstack/react-query";

import { Card, CardContent, CardDescription, CardHeader, CardTitle, PageHeader, ProductPage } from "@ta/ui";

import { supabase } from "@/lib/supabase/client";

export default function PlatformSettingsPage() {
  const query = useQuery({
    queryKey: ["admin", "platform-settings"],
    queryFn: async () => {
      const { data, error } = await supabase.from("platform_settings").select("*").order("key");
      if (error) throw error;
      return data ?? [];
    },
  });

  return (
    <ProductPage size="xl">
      <PageHeader
        eyebrow="System"
        title="Platform settings"
        description="Read operational flags and backend guard settings. Mutations should stay behind audited Edge Functions."
      />
      <Card className="border-border/70 bg-card/70">
        <CardHeader>
          <CardTitle>Settings registry</CardTitle>
          <CardDescription>Some environments may expose this table only to service-role functions.</CardDescription>
        </CardHeader>
        <CardContent>
          {query.isLoading ? <div className="text-sm text-muted-foreground">Loading settings...</div> : null}
          {query.isError ? <div className="text-sm text-destructive">{(query.error as Error).message}</div> : null}
          {!query.isLoading && !query.isError ? (
            <div className="grid gap-3 md:grid-cols-2">
              {(query.data ?? []).map((row) => (
                <div key={row.key} className="rounded-lg border border-border/50 bg-background/45 p-3">
                  <div className="font-mono text-sm font-bold text-foreground">{row.key}</div>
                  <pre className="mt-2 overflow-auto text-xs text-muted-foreground">{JSON.stringify(row.value, null, 2)}</pre>
                </div>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </ProductPage>
  );
}
