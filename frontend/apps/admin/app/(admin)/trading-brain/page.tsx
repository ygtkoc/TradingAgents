"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, PageHeader, ProductPage } from "@ta/ui";

import { supabase } from "@/lib/supabase/client";

const TAG_RULES: Array<[string, string[]]> = [
  ["risk", ["risk", "stop", "invalid", "rr", "reward", "loss"]],
  ["stop-loss", ["stop", "invalidation", "invalidasyon"]],
  ["take-profit", ["take profit", "tp", "profit", "kar"]],
  ["breakout", ["breakout", "kirilim", "kırılım"]],
  ["trend", ["trend", "ema", "ma", "structure"]],
  ["support", ["support", "destek"]],
  ["resistance", ["resistance", "direnc", "direnç"]],
  ["liquidity", ["liquidity", "likidite", "sweep"]],
  ["psychology", ["fomo", "fear", "greed", "discipline", "psikoloji"]],
  ["position-sizing", ["size", "sizing", "position", "lot", "miktar"]],
];

export default function AdminTradingBrainPage() {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState("note");
  const [content, setContent] = useState("");

  const sourcesQ = useQuery({
    queryKey: ["admin", "trading-brain", "sources"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("trading_knowledge_sources")
        .select("id,title,source_type,status,user_id,created_at")
        .order("created_at", { ascending: false })
        .limit(50);
      if (error) throw error;
      return data ?? [];
    },
  });

  const rulesQ = useQuery({
    queryKey: ["admin", "trading-brain", "rules"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("trading_strategy_rules")
        .select("*")
        .eq("active", true)
        .order("created_at", { ascending: false })
        .limit(120);
      if (error) throw error;
      return data ?? [];
    },
  });

  const importMutation = useMutation({
    mutationFn: async () => {
      const cleanContent = content.trim();
      if (cleanContent.length < 40) throw new Error("Content is too short.");

      const { data: source, error: sourceError } = await supabase
        .from("trading_knowledge_sources")
        .insert({
          user_id: null,
          title: title.trim() || "Global trading knowledge",
          source_type: sourceType,
          content_text: cleanContent,
          metadata: { scope: "global", imported_from: "admin_panel" },
        })
        .select("id")
        .single();
      if (sourceError || !source) throw sourceError ?? new Error("Source insert failed");

      const chunks = chunkText(cleanContent).map((chunk, index) => ({
        source_id: source.id,
        user_id: null,
        chunk_index: index,
        content: chunk,
        tags: tagsFor(chunk),
        metadata: { scope: "global" },
      }));
      const { error: chunkError } = await supabase.from("trading_knowledge_chunks").insert(chunks);
      if (chunkError) throw chunkError;

      const rules = extractRules(cleanContent).map((rule, index) => ({
        user_id: null,
        source_id: source.id,
        rule_code: `global_${source.id.slice(0, 8)}_${index + 1}`,
        title: rule.title,
        rule_text: rule.text,
        category: rule.category,
        severity: rule.severity,
        weight: rule.weight,
        metadata: { scope: "global", extracted_from: "admin_heuristic_v1" },
      }));
      if (rules.length) {
        const { error: ruleError } = await supabase.from("trading_strategy_rules").insert(rules);
        if (ruleError) throw ruleError;
      }
    },
    onSuccess: () => {
      setTitle("");
      setContent("");
      void qc.invalidateQueries({ queryKey: ["admin", "trading-brain"] });
    },
  });

  const stats = useMemo(() => {
    const rules = rulesQ.data ?? [];
    return {
      globalSources: (sourcesQ.data ?? []).filter((row) => row.user_id == null).length,
      rules: rules.length,
      critical: rules.filter((row) => row.severity === "critical" || row.severity === "high").length,
    };
  }, [rulesQ.data, sourcesQ.data]);

  return (
    <ProductPage size="xl">
      <PageHeader
        eyebrow="Global intelligence"
        title="Trading Brain"
        description="Manage the central knowledge library, extracted strategy rules, and execution gate material used by every customer bot."
      />

      <div className="grid gap-3 md:grid-cols-3">
        <Stat label="Global sources" value={String(stats.globalSources)} />
        <Stat label="Active rules" value={String(stats.rules)} />
        <Stat label="High impact rules" value={String(stats.critical)} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Import global knowledge</CardTitle>
            <CardDescription>
              Paste trading education, strategy rules, video transcript text, or post-trade lessons. These become global rules for all bots.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input placeholder="Title" value={title} onChange={(event) => setTitle(event.target.value)} />
            <select
              className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground"
              value={sourceType}
              onChange={(event) => setSourceType(event.target.value)}
            >
              <option value="note">Note</option>
              <option value="article">Article</option>
              <option value="video_transcript">Video transcript</option>
              <option value="strategy">Strategy</option>
              <option value="post_trade">Post-trade lesson</option>
            </select>
            <textarea
              className="min-h-72 w-full rounded-md border border-border bg-background px-3 py-3 font-mono text-xs text-foreground outline-none placeholder:text-muted-foreground"
              placeholder="Paste content here..."
              value={content}
              onChange={(event) => setContent(event.target.value)}
            />
            {importMutation.isError ? (
              <p className="text-sm text-destructive">{(importMutation.error as Error).message}</p>
            ) : null}
            <Button className="w-full" disabled={importMutation.isPending} onClick={() => importMutation.mutate()}>
              {importMutation.isPending ? "Importing..." : "Import globally"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Execution gate rules</CardTitle>
            <CardDescription>Rules with no owner are global and apply to every customer execution.</CardDescription>
          </CardHeader>
          <CardContent className="max-h-[620px] space-y-2 overflow-y-auto">
            {(rulesQ.data ?? []).map((rule) => (
              <div key={rule.id} className="rounded-lg border border-border/50 bg-card/50 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold text-foreground">{rule.title}</div>
                  <div className="flex items-center gap-2">
                    {rule.user_id == null ? <Badge variant="success">global</Badge> : <Badge variant="secondary">user</Badge>}
                    <Badge variant={rule.severity === "critical" || rule.severity === "high" ? "destructive" : "secondary"}>{rule.severity}</Badge>
                  </div>
                </div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{rule.rule_text}</p>
                <div className="mt-2 text-[10px] font-bold uppercase tracking-[0.12em] text-muted-foreground/60">
                  {rule.category} / weight {rule.weight}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Knowledge sources</CardTitle>
          <CardDescription>Global sources are shared by all bot executions.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 md:grid-cols-2">
          {(sourcesQ.data ?? []).map((source) => (
            <div key={source.id} className="rounded-lg border border-border/50 bg-card/40 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-foreground">{source.title}</div>
                {source.user_id == null ? <Badge variant="success">global</Badge> : <Badge variant="secondary">user</Badge>}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">{source.source_type} / {new Date(source.created_at).toLocaleString()}</div>
            </div>
          ))}
        </CardContent>
      </Card>
    </ProductPage>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
        <div className="mt-1 text-2xl font-black text-foreground">{value}</div>
      </CardContent>
    </Card>
  );
}

function chunkText(value: string) {
  const paragraphs = value.split(/\n{2,}/).map((item) => item.trim()).filter(Boolean);
  const chunks: string[] = [];
  let buffer = "";
  for (const paragraph of paragraphs.length ? paragraphs : [value]) {
    if ((buffer + "\n\n" + paragraph).length > 1200 && buffer) {
      chunks.push(buffer);
      buffer = paragraph;
    } else {
      buffer = buffer ? `${buffer}\n\n${paragraph}` : paragraph;
    }
  }
  if (buffer) chunks.push(buffer);
  return chunks.slice(0, 100);
}

function tagsFor(value: string) {
  const lower = value.toLowerCase();
  return TAG_RULES.filter(([, terms]) => terms.some((term) => lower.includes(term))).map(([tag]) => tag);
}

function extractRules(value: string) {
  const sentences = value
    .split(/(?<=[.!?])\s+|\n+/)
    .map((item) => item.trim())
    .filter((item) => item.length > 28);
  return sentences
    .filter((sentence) => /(must|should|never|avoid|required|risk|stop|invalid|rr|tp|gerek|asla|kaçın|stop|risk)/i.test(sentence))
    .slice(0, 18)
    .map((sentence) => {
      const tags = tagsFor(sentence);
      const category = tags[0] ?? "general";
      const critical = /(never|must|asla|required|zorunlu|critical)/i.test(sentence);
      return {
        title: sentence.slice(0, 70),
        text: sentence,
        category,
        severity: critical ? "high" : "medium",
        weight: critical ? 18 : 10,
      };
    });
}
