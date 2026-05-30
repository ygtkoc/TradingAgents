import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { hasSupabaseEnv, supabase } from "./src/lib/supabase";
import { label, minutesAgo, percent, rMultiple, scoreFromSummary } from "./src/lib/format";
import { fetchMarketMoves, normalizeMarketSymbol } from "./src/lib/market";
import type { BotRow, DecisionRow, MarketMove, SessionStatus, TradeRow } from "./src/types";

type Tab = "live" | "trades" | "bots";

const fallbackDecisions: DecisionRow[] = [
  {
    id: "demo-btc",
    symbol: "BTCUSDT",
    direction: "long",
    mode: "paper",
    final_decision: "open_long",
    approval_status: "auto_approved",
    score_summary: { aggregated_score: 82 },
    created_at: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
  },
  {
    id: "demo-eth",
    symbol: "ETHUSDT",
    direction: "short",
    mode: "paper",
    final_decision: "hold",
    approval_status: "pending",
    score_summary: { aggregated_score: 54 },
    created_at: new Date(Date.now() - 1000 * 60 * 19).toISOString(),
  },
  {
    id: "demo-sol",
    symbol: "SOLUSDT",
    direction: "long",
    mode: "shadow",
    final_decision: "manual_approval_required",
    approval_status: "pending",
    score_summary: { aggregated_score: 68 },
    created_at: new Date(Date.now() - 1000 * 60 * 31).toISOString(),
  },
];

const fallbackTrades: TradeRow[] = [
  {
    id: "trade-btc",
    symbol: "BTCUSDT",
    direction: "long",
    mode: "paper",
    status: "closed",
    r_multiple: 2.1,
    realized_pnl: 42,
    pnl_pct: 4.2,
    close_reason: "take_profit",
    closed_at: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
    created_at: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
  },
  {
    id: "trade-eth",
    symbol: "ETHUSDT",
    direction: "short",
    mode: "paper",
    status: "closed",
    r_multiple: -1,
    realized_pnl: -20,
    pnl_pct: -1.8,
    close_reason: "stop_loss",
    closed_at: new Date(Date.now() - 1000 * 60 * 84).toISOString(),
    created_at: new Date(Date.now() - 1000 * 60 * 160).toISOString(),
  },
];

const fallbackBots: BotRow[] = [
  {
    id: "bot-1",
    name: "BTC Momentum",
    status: "running",
    mode: "paper",
    symbol: "BTCUSDT",
    updated_at: new Date(Date.now() - 1000 * 60 * 6).toISOString(),
    created_at: new Date(Date.now() - 1000 * 60 * 600).toISOString(),
  },
  {
    id: "bot-2",
    name: "ETH Risk Scout",
    status: "warmup",
    mode: "shadow",
    symbol: "ETHUSDT",
    updated_at: new Date(Date.now() - 1000 * 60 * 24).toISOString(),
    created_at: new Date(Date.now() - 1000 * 60 * 800).toISOString(),
  },
];

const fallbackMoves: Record<string, MarketMove> = {
  BTCUSDT: { symbol: "BTCUSDT", change24h: 1.84 },
  ETHUSDT: { symbol: "ETHUSDT", change24h: -0.72 },
  SOLUSDT: { symbol: "SOLUSDT", change24h: 4.16 },
};

export default function App() {
  const [sessionStatus, setSessionStatus] = useState<SessionStatus>("loading");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("live");
  const [refreshing, setRefreshing] = useState(false);
  const [decisions, setDecisions] = useState<DecisionRow[]>(fallbackDecisions);
  const [trades, setTrades] = useState<TradeRow[]>(fallbackTrades);
  const [bots, setBots] = useState<BotRow[]>(fallbackBots);
  const [moves, setMoves] = useState<Record<string, MarketMove>>(fallbackMoves);

  useEffect(() => {
    if (!hasSupabaseEnv) {
      setSessionStatus("signed-out");
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      setSessionStatus(data.session ? "signed-in" : "signed-out");
    });

    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setSessionStatus(session ? "signed-in" : "signed-out");
    });

    return () => {
      data.subscription.unsubscribe();
    };
  }, []);

  const loadDashboard = useCallback(async () => {
    if (!hasSupabaseEnv || sessionStatus !== "signed-in") {
      return;
    }

    const [decisionResult, tradeResult, botResult] = await Promise.all([
      supabase
        .from("trade_decisions")
        .select("id,symbol,direction,mode,final_decision,approval_status,score_summary,created_at")
        .order("created_at", { ascending: false })
        .limit(8),
      supabase
        .from("trades")
        .select("id,symbol,direction,mode,status,r_multiple,realized_pnl,pnl_pct,close_reason,closed_at,created_at")
        .order("created_at", { ascending: false })
        .limit(10),
      supabase
        .from("bots")
        .select("id,name,status,mode,symbol,updated_at,created_at")
        .order("created_at", { ascending: false })
        .limit(8),
    ]);

    const nextDecisions = decisionResult.data?.length ? decisionResult.data as DecisionRow[] : fallbackDecisions;
    const nextTrades = tradeResult.data?.length ? tradeResult.data as TradeRow[] : fallbackTrades;
    const nextBots = botResult.data?.length ? botResult.data as BotRow[] : fallbackBots;
    const nextSymbols = [
      ...nextDecisions.map((decision) => decision.symbol),
      ...nextTrades.map((trade) => trade.symbol),
      ...nextBots.map((bot) => bot.symbol ?? ""),
    ].filter(Boolean);

    setDecisions(nextDecisions);
    setTrades(nextTrades);
    setBots(nextBots);
    setMoves({ ...fallbackMoves, ...(await fetchMarketMoves(nextSymbols)) });
  }, [sessionStatus]);

  useEffect(() => {
    void loadDashboard();
    const timer = setInterval(() => {
      void loadDashboard();
    }, 10_000);

    return () => clearInterval(timer);
  }, [loadDashboard]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadDashboard();
    setRefreshing(false);
  }, [loadDashboard]);

  const signIn = useCallback(async () => {
    if (!hasSupabaseEnv) {
      Alert.alert("Supabase env missing", "Copy .env.example to .env and fill Expo public Supabase values.");
      return;
    }

    setAuthLoading(true);
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    setAuthLoading(false);

    if (error) {
      Alert.alert("Sign in failed", error.message);
    }
  }, [email, password]);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
  }, []);

  const summary = useMemo(() => {
    const closedTrades = trades.filter((trade) => trade.status === "closed");
    const winners = closedTrades.filter((trade) => Number(trade.r_multiple) > 0).length;

    return {
      active: decisions.filter((decision) => decision.approval_status !== "rejected").length,
      closed: closedTrades.length,
      winners,
    };
  }, [decisions, trades]);

  if (sessionStatus === "loading") {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusBar style="light" />
        <View style={styles.centered}>
          <ActivityIndicator color="#5eead4" />
          <Text style={styles.muted}>Lucrandos loading</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (sessionStatus === "signed-out") {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusBar style="light" />
        <View style={styles.authScreen}>
          <View style={styles.logo}>
            <Text style={styles.logoText}>L</Text>
          </View>
          <Text style={styles.title}>Lucrandos</Text>
          <Text style={styles.subtitle}>Mobile command center for agent decisions, trades, and bots.</Text>
          <View style={styles.authCard}>
            <TextInput
              autoCapitalize="none"
              keyboardType="email-address"
              onChangeText={setEmail}
              placeholder="Email"
              placeholderTextColor="#71717a"
              style={styles.input}
              value={email}
            />
            <TextInput
              onChangeText={setPassword}
              placeholder="Password"
              placeholderTextColor="#71717a"
              secureTextEntry
              style={styles.input}
              value={password}
            />
            <Pressable disabled={authLoading} onPress={signIn} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>{authLoading ? "Signing in..." : "Sign in"}</Text>
            </Pressable>
            {!hasSupabaseEnv ? (
              <Text style={styles.warning}>Expo Supabase env values are not configured yet.</Text>
            ) : null}
          </View>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="light" />
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor="#5eead4" onRefresh={onRefresh} />}
      >
        <View style={styles.header}>
          <View>
            <Text style={styles.kicker}>AI trading OS</Text>
            <Text style={styles.heading}>Command center</Text>
          </View>
          <Pressable onPress={signOut} style={styles.ghostButton}>
            <Text style={styles.ghostButtonText}>Sign out</Text>
          </Pressable>
        </View>

        <View style={styles.summaryGrid}>
          <Metric label="Active" value={String(summary.active)} />
          <Metric label="Closed" value={String(summary.closed)} />
          <Metric label="Winners" value={`${summary.winners}/${summary.closed}`} />
        </View>

        <View style={styles.tabs}>
          {(["live", "trades", "bots"] as Tab[]).map((tab) => (
            <Pressable key={tab} onPress={() => setActiveTab(tab)} style={[styles.tab, activeTab === tab && styles.tabActive]}>
              <Text style={[styles.tabText, activeTab === tab && styles.tabTextActive]}>{label(tab)}</Text>
            </Pressable>
          ))}
        </View>

        {activeTab === "live" ? (
          <View style={styles.stack}>
            {decisions.map((decision) => (
              <DecisionCard key={decision.id} decision={decision} move={moves[normalizeMarketSymbol(decision.symbol)]} />
            ))}
          </View>
        ) : null}

        {activeTab === "trades" ? (
          <View style={styles.stack}>
            {trades.map((trade) => (
              <TradeCard key={trade.id} trade={trade} move={moves[normalizeMarketSymbol(trade.symbol)]} />
            ))}
          </View>
        ) : null}

        {activeTab === "bots" ? (
          <View style={styles.stack}>
            {bots.map((bot) => (
              <BotCard key={bot.id} bot={bot} move={bot.symbol ? moves[normalizeMarketSymbol(bot.symbol)] : undefined} />
            ))}
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function Metric({ label: metricLabel, value }: { label: string; value: string }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricLabel}>{metricLabel}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function DecisionCard({ decision, move }: { decision: DecisionRow; move?: MarketMove }) {
  const score = scoreFromSummary(decision.score_summary);
  const isPositive = (move?.change24h ?? 0) >= 0;

  return (
    <View style={styles.card}>
      <View style={styles.rowBetween}>
        <View>
          <Text style={styles.symbol}>{decision.symbol}</Text>
          <Text style={styles.meta}>{label(decision.mode)} / {minutesAgo(decision.created_at)} ago</Text>
        </View>
        <Badge tone={decision.final_decision.includes("open_long") ? "good" : decision.final_decision.includes("open_short") ? "bad" : "neutral"}>
          {label(decision.final_decision)}
        </Badge>
      </View>
      <View style={styles.cardFooter}>
        <Text style={styles.muted}>Score {score ?? "--"}</Text>
        <Text style={isPositive ? styles.goodText : styles.badText}>{percent(move?.change24h)} 24h</Text>
      </View>
    </View>
  );
}

function TradeCard({ trade, move }: { trade: TradeRow; move?: MarketMove }) {
  const isWinner = Number(trade.r_multiple) >= 0;
  const isPositiveMove = (move?.change24h ?? 0) >= 0;

  return (
    <View style={styles.card}>
      <View style={styles.rowBetween}>
        <View>
          <Text style={styles.symbol}>{trade.symbol}</Text>
          <Text style={styles.meta}>{label(trade.status)} / {label(trade.close_reason)} / {minutesAgo(trade.closed_at ?? trade.created_at)} ago</Text>
        </View>
        <Text style={isWinner ? styles.rGood : styles.rBad}>{rMultiple(trade.r_multiple)}</Text>
      </View>
      <View style={styles.cardFooter}>
        <Text style={styles.muted}>{label(trade.mode)}</Text>
        <Text style={isPositiveMove ? styles.goodText : styles.badText}>{percent(move?.change24h)} 24h</Text>
      </View>
    </View>
  );
}

function BotCard({ bot, move }: { bot: BotRow; move?: MarketMove }) {
  const isRunning = bot.status === "running" || bot.status === "active";
  const isPositiveMove = (move?.change24h ?? 0) >= 0;

  return (
    <View style={styles.card}>
      <View style={styles.rowBetween}>
        <View>
          <Text style={styles.symbol}>{bot.name}</Text>
          <Text style={styles.meta}>{bot.symbol ?? "MULTI"} / {label(bot.mode)} / {minutesAgo(bot.updated_at ?? bot.created_at)} ago</Text>
        </View>
        <Badge tone={isRunning ? "good" : "neutral"}>{label(bot.status)}</Badge>
      </View>
      {bot.symbol ? (
        <View style={styles.cardFooter}>
          <Text style={styles.muted}>{bot.symbol}</Text>
          <Text style={isPositiveMove ? styles.goodText : styles.badText}>{percent(move?.change24h)} 24h</Text>
        </View>
      ) : null}
    </View>
  );
}

function Badge({ children, tone }: { children: string; tone: "good" | "bad" | "neutral" }) {
  return (
    <View style={[styles.badge, tone === "good" && styles.goodBadge, tone === "bad" && styles.badBadge]}>
      <Text style={[styles.badgeText, tone === "good" && styles.goodBadgeText, tone === "bad" && styles.badBadgeText]}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#07090b",
  },
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
  },
  authScreen: {
    flex: 1,
    justifyContent: "center",
    padding: 24,
  },
  logo: {
    width: 48,
    height: 48,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(94,234,212,0.35)",
    backgroundColor: "rgba(94,234,212,0.1)",
  },
  logoText: {
    color: "#ccfbf1",
    fontSize: 18,
    fontWeight: "800",
  },
  title: {
    marginTop: 18,
    color: "#fafafa",
    fontSize: 42,
    fontWeight: "800",
  },
  subtitle: {
    marginTop: 10,
    color: "#a1a1aa",
    fontSize: 16,
    lineHeight: 24,
  },
  authCard: {
    marginTop: 28,
    gap: 12,
  },
  input: {
    height: 52,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(255,255,255,0.05)",
    color: "#fafafa",
    paddingHorizontal: 16,
    fontSize: 15,
  },
  primaryButton: {
    height: 52,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#5eead4",
  },
  primaryButtonText: {
    color: "#07100f",
    fontWeight: "800",
  },
  warning: {
    color: "#fbbf24",
    fontSize: 12,
    lineHeight: 18,
  },
  content: {
    padding: 18,
    paddingBottom: 36,
  },
  header: {
    marginTop: 8,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16,
  },
  kicker: {
    color: "#5eead4",
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 1.4,
    textTransform: "uppercase",
  },
  heading: {
    marginTop: 4,
    color: "#fafafa",
    fontSize: 34,
    fontWeight: "800",
  },
  ghostButton: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  ghostButtonText: {
    color: "#e4e4e7",
    fontWeight: "700",
  },
  summaryGrid: {
    marginTop: 22,
    flexDirection: "row",
    gap: 10,
  },
  metricCard: {
    flex: 1,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(255,255,255,0.05)",
    padding: 14,
  },
  metricLabel: {
    color: "#a1a1aa",
    fontSize: 11,
    fontWeight: "800",
    textTransform: "uppercase",
  },
  metricValue: {
    marginTop: 8,
    color: "#fafafa",
    fontSize: 24,
    fontWeight: "800",
  },
  tabs: {
    marginTop: 18,
    flexDirection: "row",
    borderRadius: 10,
    backgroundColor: "rgba(255,255,255,0.05)",
    padding: 4,
  },
  tab: {
    flex: 1,
    alignItems: "center",
    borderRadius: 8,
    paddingVertical: 10,
  },
  tabActive: {
    backgroundColor: "#f4f4f5",
  },
  tabText: {
    color: "#a1a1aa",
    fontSize: 12,
    fontWeight: "800",
  },
  tabTextActive: {
    color: "#09090b",
  },
  stack: {
    marginTop: 16,
    gap: 12,
  },
  card: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(24,24,27,0.86)",
    padding: 16,
  },
  rowBetween: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 14,
  },
  symbol: {
    color: "#fafafa",
    fontSize: 17,
    fontWeight: "800",
  },
  meta: {
    marginTop: 6,
    color: "#71717a",
    fontSize: 12,
    lineHeight: 18,
  },
  cardFooter: {
    marginTop: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  muted: {
    color: "#a1a1aa",
    fontSize: 13,
  },
  goodText: {
    color: "#a7f3d0",
    fontSize: 13,
    fontWeight: "800",
  },
  badText: {
    color: "#fecdd3",
    fontSize: 13,
    fontWeight: "800",
  },
  rGood: {
    color: "#a7f3d0",
    fontSize: 24,
    fontWeight: "900",
  },
  rBad: {
    color: "#fecdd3",
    fontSize: 24,
    fontWeight: "900",
  },
  badge: {
    maxWidth: 132,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(125,211,252,0.25)",
    backgroundColor: "rgba(125,211,252,0.1)",
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  goodBadge: {
    borderColor: "rgba(110,231,183,0.3)",
    backgroundColor: "rgba(110,231,183,0.1)",
  },
  badBadge: {
    borderColor: "rgba(251,113,133,0.3)",
    backgroundColor: "rgba(251,113,133,0.1)",
  },
  badgeText: {
    color: "#bae6fd",
    fontSize: 10,
    fontWeight: "900",
    textAlign: "center",
  },
  goodBadgeText: {
    color: "#a7f3d0",
  },
  badBadgeText: {
    color: "#fecdd3",
  },
});
