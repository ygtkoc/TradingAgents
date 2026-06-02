"use client";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorState,
  Input,
  Label,
  PageHeader,
  ProductPage,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Switch,
} from "@ta/ui";
import { formatRelative } from "@ta/utils";
import { Bot, Pause, Play, RefreshCw, Send, ShieldCheck, Smartphone } from "lucide-react";
import { useMemo, useState } from "react";

import { useTelegramSourceMutations } from "@/lib/hooks/mutations/use-telegram-source-mutations";
import { useBots } from "@/lib/hooks/queries/use-bots";
import {
  useTelegramAccounts,
  useTelegramChatOptions,
  useTelegramSignalMessages,
  useTelegramSignalSources,
} from "@/lib/hooks/queries/use-telegram-signals";

const STATUS_TONE: Record<string, string> = {
  signal_created: "bg-success/15 text-success border-success/25",
  parsed: "bg-primary/15 text-primary border-primary/25",
  rejected: "bg-destructive/15 text-destructive border-destructive/25",
  ignored: "bg-muted/50 text-muted-foreground border-border",
  failed: "bg-destructive/15 text-destructive border-destructive/25",
  pending: "bg-warning/15 text-warning border-warning/25",
};

function mutationErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Unknown error";
}

export default function TelegramSignalsPage() {
  const sources = useTelegramSignalSources();
  const messages = useTelegramSignalMessages(80);
  const accounts = useTelegramAccounts();
  const bots = useBots();
  const mutations = useTelegramSourceMutations();

  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [pendingAccountId, setPendingAccountId] = useState("");

  const [accountId, setAccountId] = useState("");
  const [botId, setBotId] = useState("");
  const [chatKey, setChatKey] = useState("");
  const [topicKey, setTopicKey] = useState("all");
  const [exchange, setExchange] = useState("binance");
  const [policy, setPolicy] = useState<"observe" | "paper" | "approval_required" | "auto">(
    "approval_required",
  );
  const [requireStopLoss, setRequireStopLoss] = useState(true);
  const [minConfidence, setMinConfidence] = useState("0.70");
  const [signalTemplate, setSignalTemplate] = useState("");
  const [templateThreshold, setTemplateThreshold] = useState("0.65");

  const chats = useTelegramChatOptions(accountId);

  const connectedAccounts = useMemo(
    () => (accounts.data ?? []).filter((a) => a.connection_status === "connected"),
    [accounts.data],
  );
  const activeBots = useMemo(
    () => (bots.data ?? []).filter((b) => !b.is_archived),
    [bots.data],
  );

  const chatRows = useMemo(
    () => (chats.data ?? []).filter((c) => !c.topic_id),
    [chats.data],
  );
  const selectedChat = chatRows.find((c) => c.chat_id === chatKey);
  const topicRows = useMemo(
    () => (chats.data ?? []).filter((c) => c.chat_id === chatKey && c.topic_id),
    [chats.data, chatKey],
  );
  const selectedTopic = topicRows.find((t) => t.topic_id === topicKey);

  const canCreate =
    accountId && botId && chatKey && !mutations.create.isPending &&
    (!selectedChat?.has_topics || topicKey !== "all" || topicRows.length === 0);

  const startAuth = () => {
    mutations.startAuth.mutate(
      { phone_number: phone, account_label: "Telegram" },
      { onSuccess: (res) => setPendingAccountId(res.account_id) },
    );
  };

  const verifyAuth = () => {
    if (!pendingAccountId) return;
    mutations.verifyAuth.mutate({
      account_id: pendingAccountId,
      phone_number: phone,
      code,
      password: password || undefined,
    });
  };

  const submit = () => {
    if (!canCreate || !selectedChat) return;
    mutations.create.mutate({
      telegram_account_id: accountId,
      bot_id: botId,
      chat_id: selectedChat.chat_id,
      chat_title: selectedChat.chat_title,
      topic_id: selectedTopic?.topic_id ?? null,
      topic_title: selectedTopic?.topic_title ?? null,
      exchange: exchange.trim() || "binance",
      execution_policy: policy,
      require_stop_loss: requireStopLoss,
      max_signal_age_minutes: 10,
      min_parse_confidence: Number(minConfidence) || 0.7,
      signal_template: signalTemplate.trim() || null,
      template_similarity_threshold: Number(templateThreshold) || 0.65,
    });
  };

  return (
    <ProductPage size="xl">
      <PageHeader
        eyebrow="Signal intake"
        title="Telegram signal router"
        description="Connect Telegram, select a group or topic, and route trade calls through parsing, policy checks, and the agent pipeline."
      />

      <div className="grid gap-5 lg:grid-cols-[400px_1fr]">
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Smartphone className="h-4 w-4 text-primary" />
                Connect Telegram
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1.5">
                <Label>Phone number</Label>
                <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+90..." />
              </div>
              <Button
                className="w-full gap-2"
                variant="outline"
                disabled={!phone || mutations.startAuth.isPending}
                onClick={startAuth}
              >
                <Send className="h-4 w-4" />
                Send code
              </Button>

              {pendingAccountId ? (
                <div className="space-y-3 rounded-lg border border-border/50 p-3">
                  <div className="space-y-1.5">
                    <Label>Telegram code</Label>
                    <Input value={code} onChange={(e) => setCode(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label>2FA password</Label>
                    <Input value={password} onChange={(e) => setPassword(e.target.value)} type="password" />
                  </div>
                  <Button className="w-full" disabled={!code || mutations.verifyAuth.isPending} onClick={verifyAuth}>
                    Verify connection
                  </Button>
                </div>
              ) : null}

              {mutations.startAuth.isError || mutations.verifyAuth.isError ? (
                <p className="text-xs text-destructive">
                  Telegram connection failed:{" "}
                  {mutationErrorMessage(mutations.startAuth.error ?? mutations.verifyAuth.error)}
                </p>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <ShieldCheck className="h-4 w-4 text-primary" />
                Signal source
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label>Telegram account</Label>
                <Select value={accountId} onValueChange={(v) => { setAccountId(v); setChatKey(""); setTopicKey("all"); }}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select connected account" />
                  </SelectTrigger>
                  <SelectContent>
                    {connectedAccounts.map((account) => (
                      <SelectItem key={account.id} value={account.id}>
                        {account.account_label} {account.phone_hint ?? ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <Button
                variant="outline"
                className="w-full gap-2"
                disabled={!accountId || mutations.refreshChats.isPending}
                onClick={() => mutations.refreshChats.mutate({ account_id: accountId })}
              >
                <RefreshCw className="h-4 w-4" />
                Refresh groups
              </Button>

              <div className="space-y-1.5">
                <Label>Group / channel</Label>
                <Select value={chatKey} onValueChange={(v) => { setChatKey(v); setTopicKey("all"); }}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select group" />
                  </SelectTrigger>
                  <SelectContent>
                    {chatRows.map((chat) => (
                      <SelectItem key={chat.chat_id} value={chat.chat_id}>
                        {chat.chat_title}{chat.has_topics ? " · topics" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {selectedChat?.has_topics && topicRows.length > 0 ? (
                <div className="space-y-1.5">
                  <Label>Topic</Label>
                  <Select value={topicKey} onValueChange={setTopicKey}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select topic" />
                    </SelectTrigger>
                    <SelectContent>
                      {topicRows.map((topic) => (
                        <SelectItem key={topic.topic_id ?? topic.id} value={topic.topic_id ?? topic.id}>
                          {topic.topic_title || topic.topic_id}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : null}

              <div className="space-y-1.5">
                <Label>Bot</Label>
                <Select value={botId} onValueChange={setBotId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select execution bot" />
                  </SelectTrigger>
                  <SelectContent>
                    {activeBots.map((bot) => (
                      <SelectItem key={bot.id} value={bot.id}>
                        {bot.name} · {bot.mode}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Exchange</Label>
                  <Input value={exchange} onChange={(e) => setExchange(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label>Min confidence</Label>
                  <Input value={minConfidence} onChange={(e) => setMinConfidence(e.target.value)} />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label>Message template</Label>
                <textarea
                  value={signalTemplate}
                  onChange={(e) => setSignalTemplate(e.target.value)}
                  placeholder={"#BTCUSDT LONG\nEntry: 66200 - 66800\nTP1: 67500\nSL: 64800"}
                  className="min-h-28 w-full resize-y rounded-md border border-border/65 bg-card/70 px-3 py-2 text-[13px] leading-relaxed text-foreground placeholder:text-muted-foreground/40 transition-all duration-150 hover:border-border focus-visible:border-ring/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
                />
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  Incoming messages from this source must look similar to this example before a signal is created.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label>Template match</Label>
                <Input value={templateThreshold} onChange={(e) => setTemplateThreshold(e.target.value)} />
              </div>

              <div className="space-y-1.5">
                <Label>Policy</Label>
                <Select value={policy} onValueChange={(v) => setPolicy(v as typeof policy)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="approval_required">Approval required</SelectItem>
                    <SelectItem value="paper">Paper only</SelectItem>
                    <SelectItem value="observe">Observe only</SelectItem>
                    <SelectItem value="auto">Auto</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between rounded-lg border border-border/50 px-3 py-2">
                <div>
                  <div className="text-[13px] font-medium">Require stop-loss</div>
                  <div className="text-[11px] text-muted-foreground">Reject signals without SL.</div>
                </div>
                <Switch checked={requireStopLoss} onCheckedChange={setRequireStopLoss} />
              </div>

              {mutations.create.isError ? (
                <p className="text-xs text-destructive">Source could not be saved.</p>
              ) : null}

              <Button className="w-full gap-2" disabled={!canCreate} onClick={submit}>
                <Send className="h-4 w-4" />
                Add source
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Active sources</CardTitle>
            </CardHeader>
            <CardContent>
              {sources.isLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-14 w-full" />
                  <Skeleton className="h-14 w-full" />
                </div>
              ) : sources.isError ? (
                <ErrorState onRetry={() => void sources.refetch()} />
              ) : !sources.data?.length ? (
                <EmptyState icon={Bot} title="No Telegram sources" description="Connect an account and choose a group." />
              ) : (
                <div className="divide-y divide-border/40">
                  {sources.data.map((source) => (
                    <div key={source.id} className="flex items-center justify-between gap-4 py-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm font-semibold">
                            {source.chat_title || source.chat_id}
                            {source.topic_title ? ` / ${source.topic_title}` : ""}
                          </span>
                          <Badge variant="outline">{source.execution_policy}</Badge>
                          {!source.enabled ? <Badge variant="secondary">Paused</Badge> : null}
                        </div>
                        <div className="mt-0.5 truncate text-xs text-muted-foreground">
                          {source.exchange} · min {source.min_parse_confidence} · SL {source.require_stop_loss ? "required" : "optional"} · cross/max leverage
                        </div>
                        {source.signal_template ? (
                          <div className="mt-0.5 truncate text-xs text-muted-foreground">
                            template match {source.template_similarity_threshold}
                          </div>
                        ) : null}
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5"
                        disabled={mutations.toggle.isPending}
                        onClick={() => mutations.toggle.mutate({ id: source.id, enabled: !source.enabled })}
                      >
                        {source.enabled ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                        {source.enabled ? "Pause" : "Start"}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Inbox</CardTitle>
            </CardHeader>
            <CardContent>
              {messages.isLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-20 w-full" />
                  ))}
                </div>
              ) : messages.isError ? (
                <ErrorState onRetry={() => void messages.refetch()} />
              ) : !messages.data?.length ? (
                <EmptyState icon={Send} title="No messages yet" description="Parsed Telegram messages will appear here." />
              ) : (
                <div className="space-y-2">
                  {messages.data.map((message) => {
                    const normalized = message.normalized_signal ?? {};
                    return (
                      <div key={message.id} className="rounded-lg border border-border/40 bg-card/40 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge className={STATUS_TONE[message.parse_status] ?? ""} variant="outline">
                                {message.parse_status}
                              </Badge>
                              <span className="text-sm font-semibold">
                                {String(normalized.symbol ?? "Unknown")}
                              </span>
                              <span className="text-xs text-muted-foreground">
                                {String(normalized.direction ?? "-")}
                              </span>
                            </div>
                            <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                              {message.raw_text}
                            </p>
                            {message.parse_error ? (
                              <p className="mt-1 text-xs text-destructive">{message.parse_error}</p>
                            ) : null}
                          </div>
                          <span className="shrink-0 text-[11px] text-muted-foreground/70">
                            {formatRelative(message.received_at)}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </ProductPage>
  );
}
