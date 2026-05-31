"use client";

import { useMemo, useState } from "react";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@ta/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { supabase } from "@/lib/supabase/client";
import { useCurrentUser } from "@/lib/hooks/queries/use-current-user";

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

export default function TradingBrainPage() {
  const { data: user } = useCurrentUser();
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState("note");
  const [content, setContent] = useState("");

  const sourcesQ = useQuery({
    queryKey: ["trading-brain", "sources", user?.id],
    enabled: !!user,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("trading_knowledge_sources")
        .select("id,title,source_type,status,created_at")
        .order("created_at", { ascending: false })
        .limit(30);
      if (error) throw error;
      return data ?? [];
    },
  });

  const rulesQ = useQuery({
    queryKey: ["trading-brain", "rules", user?.id],
    enabled: !!user,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("trading_strategy_rules")
        .select("*")
        .eq("active", true)
        .order("created_at", { ascending: false })
        .limit(80);
      if (error) throw error;
      return data ?? [];
    },
  });

  const importMutation = useMutation({
    mutationFn: async () => {
      if (!user) throw new Error("Not signed in");
      const cleanTitle = title.trim() || "Untitled trading note";
      const cleanContent = content.trim();
      if (cleanContent.length < 40) throw new Error("Content is too short.");

      const { data: source, error: sourceError } = await supabase
        .from("trading_knowledge_sources")
        .insert({
          user_id: user.id,
          title: cleanTitle,
          source_type: sourceType,
          content_text: cleanContent,
          metadata: { imported_from: "customer_dashboard" },
        })
        .select("id")
        .single();
      if (sourceError || !source) throw sourceError ?? new Error("Source insert failed");

      const chunks = chunkText(cleanContent).map((chunk, index) => ({
        source_id: source.id,
        user_id: user.id,
        chunk_index: index,
        content: chunk,
        tags: tagsFor(chunk),
      }));

      const { error: chunkError } = await supabase.from("trading_knowledge_chunks").insert(chunks);
      if (chunkError) throw chunkError;

      const extracted = extractRules(cleanContent).map((rule, index) => ({
        user_id: user.id,
        source_id: source.id,
        rule_code: `user_${source.id.slice(0, 8)}_${index + 1}`,
        title: rule.title,
        rule_text: rule.text,
        category: rule.category,
        severity: rule.severity,
        weight: rule.weight,
        metadata: { extracted_from: "heuristic_v1" },
      }));
      if (extracted.length) {
        const { error: ruleError } = await supabase.from("trading_strategy_rules").insert(extracted);
        if (ruleError) throw ruleError;
      }
    },
    onSuccess: () => {
      setTitle("");
      setContent("");
      void qc.invalidateQueries({ queryKey: ["trading-brain"] });
    },
  });

  const stats = useMemo(() => {
    const rules = rulesQ.data ?? [];
    return {
      sources: sourcesQ.data?.length ?? 0,
      rules: rules.length,
      critical: rules.filter((rule) => rule.severity === "critical").length,
    };
  }, [rulesQ.data, sourcesQ.data]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-[0] text-foreground">Trading Brain</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Import strategy material, extract rules, and let the execution gate critique every trade before it opens.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Stat label="Sources" value={String(stats.sources)} />
        <Stat label="Active rules" value={String(stats.rules)} />
        <Stat label="Critical rules" value={String(stats.critical)} />
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Import knowledge</CardTitle>
            <CardDescription>Paste article text, notes, or a video transcript. v1 extracts deterministic rules and searchable chunks.</CardDescription>
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
              className="min-h-64 font-mono text-xs"
              placeholder="Paste trading education, strategy notes, risk rules, or transcript text..."
              value={content}
              onChange={(event) => setContent(event.target.value)}
            />
            {importMutation.isError ? (
              <p className="text-sm text-destructive">{(importMutation.error as Error).message}</p>
            ) : null}
            <Button disabled={importMutation.isPending} onClick={() => importMutation.mutate()} className="w-full">
              {importMutation.isPending ? "Importing..." : "Import into Trading Brain"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Active strategy rules</CardTitle>
            <CardDescription>These rules are used by the execution knowledge gate.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {(rulesQ.data ?? []).map((rule) => (
              <div key={rule.id} className="rounded-lg border border-border/50 bg-card/50 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold text-foreground">{rule.title}</div>
                  <Badge variant={rule.severity === "critical" || rule.severity === "high" ? "destructive" : "secondary"}>{rule.severity}</Badge>
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
          <CardTitle>Imported sources</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 md:grid-cols-2">
          {(sourcesQ.data ?? []).map((source) => (
            <div key={source.id} className="rounded-lg border border-border/50 bg-card/40 p-3">
              <div className="font-semibold text-foreground">{source.title}</div>
              <div className="mt-1 text-xs text-muted-foreground">{source.source_type} / {new Date(source.created_at).toLocaleString()}</div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
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
  return chunks.slice(0, 80);
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
    .slice(0, 12)
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
