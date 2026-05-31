import { StatusBar } from "expo-status-bar";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Animated,
  Easing,
  KeyboardAvoidingView,
  Platform,
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

type Tab = "overview" | "decisions" | "positions" | "bots" | "paper" | "account";
type WalletMode = "paper" | "binance" | "bybit" | "okx";
type Screen =
  | { name: "home" }
  | { name: "decision"; id: string }
  | { name: "trade"; id: string };

type PaperAccount = {
  starting_balance: number;
  balance: number;
  reserved_balance: number;
  available_balance: number;
  realized_pnl: number;
  unrealized_pnl: number;
  equity: number;
  status: string;
};

type ExchangeAccount = {
  id: string;
  exchange?: string | null;
  label?: string | null;
  is_active?: boolean | null;
  can_trade?: boolean | null;
};

type ManualAction = "set_stop_loss" | "set_take_profit" | "move_stop_to_entry" | "close_percent" | "close_full" | "reduce_quantity";
type BotAction = "activate" | "pause" | "archive";

const walletOptions: { key: WalletMode; label: string }[] = [
  { key: "paper", label: "Paper" },
  { key: "binance", label: "Binance" },
  { key: "bybit", label: "ByBit" },
  { key: "okx", label: "OKX" },
];

const fallbackDecisions: DecisionRow[] = [
  {
    id: "demo-btc",
    symbol: "BTCUSDT",
    direction: "long",
    mode: "paper",
    final_decision: "open_long",
    approval_status: "auto_approved",
    manual_approval_required: false,
    score_summary: { aggregated_score: 82 },
    risk_summary: { risk: "normal", max_position_pct: 1.5 },
    security_summary: { verdict: "clear" },
    created_at: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
  },
  {
    id: "demo-sol",
    symbol: "SOLUSDT",
    direction: "long",
    mode: "paper",
    final_decision: "open_long",
    approval_status: "pending",
    manual_approval_required: true,
    score_summary: { aggregated_score: 68 },
    risk_summary: { risk: "needs review" },
    security_summary: { verdict: "manual approval" },
    created_at: new Date(Date.now() - 1000 * 60 * 31).toISOString(),
  },
];

const fallbackTrades: TradeRow[] = [
  {
    id: "trade-btc",
    symbol: "BTCUSDT",
    direction: "long",
    mode: "paper",
    status: "open",
    lifecycle_status: "open",
    quantity: 0.002,
    filled_quantity: 0.002,
    entry_price: 104000,
    avg_fill_price: 104000,
    stop_loss: 102600,
    take_profit: 107200,
    r_multiple: null,
    realized_pnl: 0,
    pnl_pct: null,
    close_reason: null,
    metadata: {
      reward_plan: {
        take_profits: [
          { target_price: 105500, r_multiple: 1, size_pct: 33 },
          { target_price: 107200, r_multiple: 2, size_pct: 33 },
          { target_price: 109000, r_multiple: 3, size_pct: 34 },
        ],
      },
    },
    closed_at: null,
    created_at: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
  },
  {
    id: "trade-eth",
    symbol: "ETHUSDT",
    direction: "short",
    mode: "paper",
    status: "closed",
    lifecycle_status: "closed",
    quantity: 0.03,
    entry_price: 3400,
    exit_price: 3332,
    r_multiple: 2,
    realized_pnl: 20.4,
    pnl_pct: 2,
    close_reason: "take_profit",
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
];

const fallbackMoves: Record<string, MarketMove> = {
  BTCUSDT: { symbol: "BTCUSDT", change24h: 1.84, lastPrice: 105240 },
  ETHUSDT: { symbol: "ETHUSDT", change24h: -0.72, lastPrice: 3332 },
  SOLUSDT: { symbol: "SOLUSDT", change24h: 4.16, lastPrice: 163.4 },
};

const tabs: { key: Tab; label: string }[] = [
  { key: "overview", label: "Home" },
  { key: "decisions", label: "Decisions" },
  { key: "positions", label: "Positions" },
  { key: "bots", label: "Bots" },
  { key: "paper", label: "Paper" },
  { key: "account", label: "Account" },
];

export default function App() {
  const [sessionStatus, setSessionStatus] = useState<SessionStatus>("loading");
  const [email, setEmail] = useState("");
  const [accountEmail, setAccountEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [wallet, setWallet] = useState<WalletMode>("paper");
  const [screen, setScreen] = useState<Screen>({ name: "home" });
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("Rejected from mobile review.");
  const [actionError, setActionError] = useState<string | null>(null);
  const [manualPrice, setManualPrice] = useState("");
  const [manualQuantity, setManualQuantity] = useState("");
  const [manualPercent, setManualPercent] = useState("50");
  const [manualStop, setManualStop] = useState("");
  const [manualTakeProfit, setManualTakeProfit] = useState("");
  const [decisions, setDecisions] = useState<DecisionRow[]>(fallbackDecisions);
  const [trades, setTrades] = useState<TradeRow[]>(fallbackTrades);
  const [bots, setBots] = useState<BotRow[]>(fallbackBots);
  const [paperAccount, setPaperAccount] = useState<PaperAccount | null>(null);
  const [exchanges, setExchanges] = useState<ExchangeAccount[]>([]);
  const [moves, setMoves] = useState<Record<string, MarketMove>>(fallbackMoves);
  const [routeAnim] = useState(() => new Animated.Value(1));

  useEffect(() => {
    routeAnim.setValue(0);
    Animated.timing(routeAnim, {
      toValue: 1,
      duration: 240,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [activeTab, routeAnim, screen]);

  useEffect(() => {
    if (!hasSupabaseEnv) {
      setSessionStatus("signed-out");
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      setSessionStatus(data.session ? "signed-in" : "signed-out");
      setAccountEmail(data.session?.user.email ?? "");
    });

    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setSessionStatus(session ? "signed-in" : "signed-out");
      setAccountEmail(session?.user.email ?? "");
    });

    return () => {
      data.subscription.unsubscribe();
    };
  }, []);

  const loadDashboard = useCallback(async () => {
    if (!hasSupabaseEnv || sessionStatus !== "signed-in") {
      return;
    }

    const userResult = await supabase.auth.getUser();
    const userId = userResult.data.user?.id;

    if (!userId) {
      return;
    }

    const [decisionResult, tradeResult, botResult, paperResult, exchangeResult] = await Promise.all([
      supabase
        .from("trade_decisions")
        .select("*")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(30),
      supabase
        .from("trades")
        .select("*")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(50),
      supabase
        .from("bots")
        .select("id,user_id,name,status,mode,symbol,updated_at,created_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(20),
      supabase.from("paper_accounts").select("*").eq("user_id", userId).maybeSingle(),
      supabase
        .from("exchange_accounts")
        .select("id,exchange,label,is_active,can_trade")
        .eq("user_id", userId)
        .order("created_at", { ascending: false }),
    ]);

    if (decisionResult.error) console.warn("mobile.decisions.failed", decisionResult.error.message);
    if (tradeResult.error) console.warn("mobile.trades.failed", tradeResult.error.message);
    if (botResult.error) console.warn("mobile.bots.failed", botResult.error.message);
    if (paperResult.error) console.warn("mobile.paper.failed", paperResult.error.message);
    if (exchangeResult.error) console.warn("mobile.exchanges.failed", exchangeResult.error.message);

    const nextDecisions = decisionResult.data ? (decisionResult.data as DecisionRow[]) : fallbackDecisions;
    const nextTrades = tradeResult.data ? (tradeResult.data as TradeRow[]) : fallbackTrades;
    const nextBots = botResult.data ? (botResult.data as BotRow[]) : fallbackBots;
    const nextSymbols = [
      ...nextDecisions.map((decision) => decision.symbol),
      ...nextTrades.map((trade) => trade.symbol),
      ...nextBots.map((bot) => bot.symbol ?? ""),
    ].filter(Boolean);

    setDecisions(nextDecisions);
    setTrades(nextTrades);
    setBots(nextBots);
    setPaperAccount(normalizePaperAccount(paperResult.data as Record<string, unknown> | null));
    setExchanges((exchangeResult.data ?? []) as ExchangeAccount[]);
    setMoves({ ...fallbackMoves, ...(await fetchMarketMoves(nextSymbols)) });
  }, [sessionStatus]);

  useEffect(() => {
    void loadDashboard();
    const timer = setInterval(() => {
      void loadDashboard();
    }, 3_000);

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
    setScreen({ name: "home" });
  }, []);

  const navigateHome = useCallback(() => setScreen({ name: "home" }), []);
  const openDecision = useCallback((id: string) => setScreen({ name: "decision", id }), []);
  const openTrade = useCallback((id: string) => setScreen({ name: "trade", id }), []);

  const resetPaperAccount = useCallback(() => {
    Alert.alert(
      "Reset paper account",
      "This clears paper positions, decisions, account events, and resets the simulated balance.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Reset",
          style: "destructive",
          onPress: async () => {
            setBusy("paper-reset");
            const userResult = await supabase.auth.getUser();
            const userId = userResult.data.user?.id;
            if (!userId) {
              setBusy(null);
              Alert.alert("Not signed in", "Please sign in again.");
              return;
            }

            const { error: edgeError } = await supabase.functions.invoke("paper-account-reset", { body: {} });
            if (!edgeError) {
              setBusy(null);
              await loadDashboard();
              return;
            }

            const { error: rpcError } = await (supabase as any).rpc("paper_reset", {
              p_user_id: userId,
              p_starting_balance: null,
            });
            setBusy(null);

            if (rpcError) {
              Alert.alert("Reset failed", rpcError.message || edgeError.message);
              return;
            }

            await loadDashboard();
          },
        },
      ],
    );
  }, [loadDashboard]);

  const transitionStyle = {
    opacity: routeAnim,
    transform: [
      {
        translateY: routeAnim.interpolate({
          inputRange: [0, 1],
          outputRange: [16, 0],
        }),
      },
    ],
  };

  const selectedDecision = screen.name === "decision" ? decisions.find((decision) => decision.id === screen.id) : null;
  const selectedTrade = screen.name === "trade" ? trades.find((trade) => trade.id === screen.id) : null;

  const walletTrades = useMemo(() => {
    if (wallet === "paper") {
      return trades.filter((trade) => (trade.mode ?? "paper") === "paper");
    }
    return trades.filter((trade) => {
      const meta = trade.metadata ?? {};
      const exchange = String(meta.exchange ?? meta.exchange_name ?? "").toLowerCase();
      return exchange === wallet || (trade.mode === "live" && exchange === "");
    });
  }, [trades, wallet]);

  const portfolio = useMemo(() => {
    const livePnl = walletTrades
      .filter((trade) => isTradeOpen(trade))
      .reduce((sum, trade) => sum + livePnlForTrade(trade, moves).pnl, 0);
    const realized = walletTrades.reduce((sum, trade) => sum + toNumber(trade.realized_pnl), 0);
    const equity = wallet === "paper" && paperAccount ? paperAccount.equity || paperAccount.balance : realized + livePnl;
  const base = wallet === "paper" && paperAccount ? paperAccount.starting_balance || paperAccount.balance : Math.abs(realized) + Math.abs(livePnl);
    const pnlPct = base > 0 ? ((realized + livePnl) / base) * 100 : 0;

    return {
      equity,
      available: wallet === "paper" && paperAccount ? paperAccount.available_balance : null,
      reserved: wallet === "paper" && paperAccount ? paperAccount.reserved_balance : null,
      realized,
      livePnl,
      pnlPct,
      openCount: walletTrades.filter(isTradeOpen).length,
    };
  }, [moves, paperAccount, wallet, walletTrades]);

  const approveDecision = useCallback(async (decisionId: string) => {
    setBusy(`approve-${decisionId}`);
    const { error } = await supabase.functions.invoke("manual-trade-approval", {
      body: { trade_decision_id: decisionId, action: "approve" },
    });
    setBusy(null);
    if (error) {
      Alert.alert("Approve failed", error.message);
      return;
    }
    await loadDashboard();
  }, [loadDashboard]);

  const rejectDecision = useCallback(async (decisionId: string) => {
    const reason = rejectReason.trim();
    if (!reason) {
      Alert.alert("Reason required", "Please add a short rejection reason.");
      return;
    }
    setBusy(`reject-${decisionId}`);
    const { error } = await supabase.functions.invoke("manual-trade-approval", {
      body: { trade_decision_id: decisionId, action: "reject", rejection_reason: reason },
    });
    setBusy(null);
    if (error) {
      Alert.alert("Reject failed", error.message);
      return;
    }
    await loadDashboard();
  }, [loadDashboard, rejectReason]);

  const runManualTradeAction = useCallback(async (trade: TradeRow, action: ManualAction) => {
    setActionError(null);
    setBusy(`trade-${action}`);

    const currentPrice = moveForTrade(trade, moves)?.lastPrice ?? entryPrice(trade);
    const payload = {
      p_trade_id: trade.id,
      p_action: action,
      p_quantity: action === "reduce_quantity" ? parseNumber(manualQuantity) : null,
      p_percent: action === "close_percent" ? parseNumber(manualPercent) : action === "close_full" ? 100 : null,
      p_price: action === "close_percent" || action === "close_full" || action === "reduce_quantity"
        ? parseNumber(manualPrice) ?? currentPrice
        : null,
      p_stop_loss: action === "set_stop_loss" ? parseNumber(manualStop) : null,
      p_take_profit: action === "set_take_profit" ? parseNumber(manualTakeProfit) : null,
    };

    const { error } = await (supabase as any).rpc("manual_trade_action", payload);
    setBusy(null);

    if (error) {
      setActionError(formatManualActionError(error.message));
      return;
    }

    await loadDashboard();
  }, [loadDashboard, manualPercent, manualPrice, manualQuantity, manualStop, manualTakeProfit, moves]);

  const runBotAction = useCallback(async (bot: BotRow, action: BotAction) => {
    setBusy(`bot-${action}-${bot.id}`);
    const functionName = action === "activate" ? "bots-activate" : action === "pause" ? "bots-pause" : "bots-archive";
    const { error } = await supabase.functions.invoke(functionName, { body: { bot_id: bot.id } });
    setBusy(null);
    if (error) {
      Alert.alert("Bot action failed", error.message);
      return;
    }
    await loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    if (selectedTrade) {
      const current = moveForTrade(selectedTrade, moves)?.lastPrice ?? entryPrice(selectedTrade);
      const qty = quantityForTrade(selectedTrade);
      setManualPrice(current ? String(trimNumber(current)) : "");
      setManualQuantity(qty ? String(trimNumber(qty * 0.25)) : "");
      setManualPercent("50");
      setManualStop(selectedTrade.stop_loss != null ? String(selectedTrade.stop_loss) : "");
      setManualTakeProfit(selectedTrade.take_profit != null ? String(selectedTrade.take_profit) : "");
      setActionError(null);
    }
  }, [moves, selectedTrade?.id]);

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
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.keyboardScreen}>
          <ScrollView contentContainerStyle={styles.authContent} keyboardShouldPersistTaps="handled">
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
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  if (selectedDecision) {
    return (
      <Shell title={selectedDecision.symbol} subtitle="Decision detail" onBack={navigateHome} transitionStyle={transitionStyle}>
        <DecisionDetail
          busy={busy}
          decision={selectedDecision}
          move={moves[normalizeMarketSymbol(selectedDecision.symbol)]}
          onApprove={approveDecision}
          onReject={rejectDecision}
          rejectReason={rejectReason}
          setRejectReason={setRejectReason}
        />
      </Shell>
    );
  }

  if (selectedTrade) {
    return (
      <Shell title={selectedTrade.symbol} subtitle="Position detail" onBack={navigateHome} transitionStyle={transitionStyle}>
        <TradeDetail
          actionError={actionError}
          busy={busy}
          manualPercent={manualPercent}
          manualPrice={manualPrice}
          manualQuantity={manualQuantity}
          manualStop={manualStop}
          manualTakeProfit={manualTakeProfit}
          move={moveForTrade(selectedTrade, moves)}
          onAction={(action) => runManualTradeAction(selectedTrade, action)}
          setManualPercent={setManualPercent}
          setManualPrice={setManualPrice}
          setManualQuantity={setManualQuantity}
          setManualStop={setManualStop}
          setManualTakeProfit={setManualTakeProfit}
          trade={selectedTrade}
        />
      </Shell>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="light" />
      <Animated.ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor="#5eead4" onRefresh={onRefresh} />}
        style={transitionStyle}
      >
        <View style={styles.header}>
          <View style={styles.headerCopy}>
            <Text style={styles.kicker}>Lucrandos AI trading OS</Text>
            <Text style={styles.heading}>Command</Text>
          </View>
          <Pressable onPress={signOut} style={styles.ghostButton}>
            <Text style={styles.ghostButtonText}>Sign out</Text>
          </Pressable>
        </View>

        <WalletSelector exchanges={exchanges} selected={wallet} setSelected={setWallet} />
        <WalletSummary portfolio={portfolio} wallet={wallet} />

        <LiquidTabs activeTab={activeTab} setActiveTab={setActiveTab} />

        {activeTab === "overview" ? (
          <View style={styles.stack}>
            <SectionTitle title="Live positions" value={`${portfolio.openCount} open`} />
            {walletTrades.filter(isTradeOpen).slice(0, 6).map((trade) => (
              <TradeCard key={trade.id} trade={trade} move={moveForTrade(trade, moves)} onPress={() => openTrade(trade.id)} />
            ))}
            <SectionTitle title="Manual approvals" value={`${decisions.filter(isPendingManualDecision).length} pending`} />
            {decisions.filter(isPendingManualDecision).slice(0, 5).map((decision) => (
              <DecisionCard key={decision.id} decision={decision} move={moves[normalizeMarketSymbol(decision.symbol)]} onPress={() => openDecision(decision.id)} />
            ))}
          </View>
        ) : null}

        {activeTab === "decisions" ? (
          <View style={styles.stack}>
            {decisions.map((decision) => (
              <DecisionCard key={decision.id} decision={decision} move={moves[normalizeMarketSymbol(decision.symbol)]} onPress={() => openDecision(decision.id)} />
            ))}
          </View>
        ) : null}

        {activeTab === "positions" ? (
          <View style={styles.stack}>
            {walletTrades.map((trade) => (
              <TradeCard key={trade.id} trade={trade} move={moveForTrade(trade, moves)} onPress={() => openTrade(trade.id)} />
            ))}
          </View>
        ) : null}

        {activeTab === "bots" ? (
          <View style={styles.stack}>
            {bots.map((bot) => (
              <BotCard
                key={bot.id}
                bot={bot}
                busy={busy}
                move={bot.symbol ? moves[normalizeMarketSymbol(bot.symbol)] : undefined}
                onAction={runBotAction}
              />
            ))}
          </View>
        ) : null}

        {activeTab === "paper" ? (
          <PaperControls
            busy={busy}
            paperAccount={paperAccount}
            portfolio={portfolio}
            resetPaperAccount={resetPaperAccount}
            walletTrades={walletTrades}
          />
        ) : null}

        {activeTab === "account" ? (
          <AccountPanel email={accountEmail || email} exchanges={exchanges} onSignOut={signOut} paperAccount={paperAccount} />
        ) : null}
      </Animated.ScrollView>
    </SafeAreaView>
  );
}

function Shell({
  children,
  onBack,
  subtitle,
  title,
  transitionStyle,
}: {
  children: React.ReactNode;
  onBack: () => void;
  subtitle: string;
  title: string;
  transitionStyle: object;
}) {
  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="light" />
      <Animated.ScrollView contentContainerStyle={styles.content} style={transitionStyle}>
        <View style={styles.header}>
          <View style={styles.headerCopy}>
            <Text style={styles.kicker}>{subtitle}</Text>
            <Text style={styles.headingSmall}>{title}</Text>
          </View>
          <Pressable onPress={onBack} style={styles.ghostButton}>
            <Text style={styles.ghostButtonText}>Back</Text>
          </Pressable>
        </View>
        {children}
      </Animated.ScrollView>
    </SafeAreaView>
  );
}

function WalletSelector({
  exchanges,
  selected,
  setSelected,
}: {
  exchanges: ExchangeAccount[];
  selected: WalletMode;
  setSelected: (wallet: WalletMode) => void;
}) {
  return (
    <View style={styles.walletWrap}>
      <Text style={styles.sectionLabel}>Wallet</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View style={styles.walletRow}>
          {walletOptions.map((option) => {
            const isSelected = option.key === selected;
            const connected = option.key === "paper" || exchanges.some((item) => exchangeName(item) === option.key);
            return (
              <Pressable
                key={option.key}
                onPress={() => setSelected(option.key)}
                style={[styles.walletChip, isSelected && styles.walletChipActive]}
              >
                <Text style={[styles.walletChipText, isSelected && styles.walletChipTextActive]}>{option.label}</Text>
                <View style={[styles.dot, connected ? styles.dotGood : styles.dotMuted]} />
              </Pressable>
            );
          })}
        </View>
      </ScrollView>
    </View>
  );
}

function WalletSummary({ portfolio, wallet }: { portfolio: ReturnType<typeof usePortfolioShape>; wallet: WalletMode }) {
  return (
    <View style={styles.walletCard}>
      <View style={styles.rowBetween}>
        <View>
          <Text style={styles.metricLabel}>{label(wallet)} wallet</Text>
          <Text style={styles.walletValue}>{currency(portfolio.equity)}</Text>
        </View>
        <View style={styles.alignRight}>
          <Text style={portfolio.livePnl >= 0 ? styles.goodTextBig : styles.badTextBig}>{currency(portfolio.livePnl)}</Text>
          <Text style={portfolio.pnlPct >= 0 ? styles.goodText : styles.badText}>{percent(portfolio.pnlPct)} total</Text>
        </View>
      </View>
      <View style={styles.summaryGrid}>
        <Metric label="Available" value={portfolio.available == null ? "--" : currency(portfolio.available)} />
        <Metric label="Reserved" value={portfolio.reserved == null ? "--" : currency(portfolio.reserved)} />
        <Metric label="Realized" value={currency(portfolio.realized)} />
      </View>
    </View>
  );
}

function LiquidTabs({ activeTab, setActiveTab }: { activeTab: Tab; setActiveTab: (tab: Tab) => void }) {
  return (
    <View style={styles.liquidTabs}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View style={styles.liquidTabsRow}>
          {tabs.map((tab) => {
            const active = activeTab === tab.key;
            return (
              <Pressable
                key={tab.key}
                onPress={() => setActiveTab(tab.key)}
                style={[styles.liquidTab, active && styles.liquidTabActive]}
              >
                <Text style={[styles.liquidTabText, active && styles.liquidTabTextActive]}>{tab.label}</Text>
              </Pressable>
            );
          })}
        </View>
      </ScrollView>
    </View>
  );
}

function PaperControls({
  busy,
  paperAccount,
  portfolio,
  resetPaperAccount,
  walletTrades,
}: {
  busy: string | null;
  paperAccount: PaperAccount | null;
  portfolio: ReturnType<typeof usePortfolioShape>;
  resetPaperAccount: () => void;
  walletTrades: TradeRow[];
}) {
  const openPaperTrades = walletTrades.filter(isTradeOpen);

  return (
    <View style={styles.stack}>
      <View style={styles.card}>
        <View style={styles.rowBetween}>
          <View>
            <Text style={styles.kicker}>Lucrandos paper trading</Text>
            <Text style={styles.symbol}>Paper account controls</Text>
            <Text style={styles.meta}>
              {paperAccount ? `${label(paperAccount.status)} / ${openPaperTrades.length} open positions` : "No paper account loaded"}
            </Text>
          </View>
          <Badge tone={paperAccount?.status === "active" ? "good" : "neutral"}>{label(paperAccount?.status ?? "missing")}</Badge>
        </View>
        <View style={styles.detailGrid}>
          <Metric label="Equity" value={currency(portfolio.equity)} />
          <Metric label="Live P&L" value={currency(portfolio.livePnl)} />
          <Metric label="Total %" value={percent(portfolio.pnlPct)} />
        </View>
        <Pressable disabled={busy === "paper-reset"} onPress={resetPaperAccount} style={styles.dangerButtonFull}>
          <Text style={styles.dangerButtonText}>{busy === "paper-reset" ? "Resetting..." : "Reset paper account"}</Text>
        </Pressable>
      </View>

      <View style={styles.card}>
        <SectionTitle title="Current paper positions" value={`${openPaperTrades.length} open`} />
        {openPaperTrades.length ? (
          openPaperTrades.slice(0, 5).map((trade) => (
            <View key={trade.id} style={styles.tpRow}>
              <Text style={styles.symbolSmall}>{trade.symbol}</Text>
              <Text style={styles.muted}>{label(trade.direction)} / {formatPrice(entryPrice(trade))}</Text>
              <Text style={styles.goodText}>{formatPrice(toNumber(trade.take_profit))}</Text>
            </View>
          ))
        ) : (
          <Text style={styles.muted}>No open paper positions.</Text>
        )}
      </View>
    </View>
  );
}

function AccountPanel({
  email,
  exchanges,
  onSignOut,
  paperAccount,
}: {
  email: string;
  exchanges: ExchangeAccount[];
  onSignOut: () => void;
  paperAccount: PaperAccount | null;
}) {
  return (
    <View style={styles.stack}>
      <View style={styles.card}>
        <View style={styles.rowBetween}>
          <View>
            <Text style={styles.kicker}>Lucrandos account</Text>
            <Text style={styles.symbol}>{email || "Signed in"}</Text>
            <Text style={styles.meta}>Mobile command center preferences and connections.</Text>
          </View>
          <View style={styles.logoSmall}>
            <Text style={styles.logoText}>L</Text>
          </View>
        </View>
        <View style={styles.detailGrid}>
          <Metric label="Paper" value={label(paperAccount?.status ?? "missing")} />
          <Metric label="Exchanges" value={String(exchanges.length)} />
          <Metric label="Mode" value="Mobile" />
        </View>
      </View>

      <View style={styles.card}>
        <SectionTitle title="Connected wallets" value={`${exchanges.length} total`} />
        {exchanges.length ? (
          exchanges.map((exchange) => (
            <View key={exchange.id} style={styles.tpRow}>
              <Text style={styles.symbolSmall}>{exchange.label || label(exchange.exchange)}</Text>
              <Text style={styles.muted}>{exchange.can_trade ? "Trading enabled" : "Read only"}</Text>
              <View style={[styles.dot, exchange.is_active ? styles.dotGood : styles.dotMuted]} />
            </View>
          ))
        ) : (
          <Text style={styles.muted}>Only Paper is active. Add exchange keys from the web dashboard when ready.</Text>
        )}
      </View>

      <Pressable onPress={onSignOut} style={styles.ghostButtonWide}>
        <Text style={styles.ghostButtonText}>Sign out</Text>
      </Pressable>
    </View>
  );
}

function usePortfolioShape() {
  return { equity: 0, available: null as number | null, reserved: null as number | null, realized: 0, livePnl: 0, pnlPct: 0, openCount: 0 };
}

function Metric({ label: metricLabel, value }: { label: string; value: string }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricLabel}>{metricLabel}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function SectionTitle({ title, value }: { title: string; value: string }) {
  return (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <Text style={styles.sectionValue}>{value}</Text>
    </View>
  );
}

function DecisionCard({ decision, move, onPress }: { decision: DecisionRow; move?: MarketMove; onPress: () => void }) {
  const score = scoreFromSummary(decision.score_summary);
  const isPositive = (move?.change24h ?? 0) >= 0;

  return (
    <Pressable onPress={onPress} style={styles.card}>
      <View style={styles.rowBetween}>
        <View style={styles.cardMain}>
          <Text style={styles.symbol}>{decision.symbol}</Text>
          <Text style={styles.meta}>{label(decision.mode)} / {minutesAgo(decision.created_at)} ago</Text>
        </View>
        <Badge tone={decision.final_decision.includes("open_long") ? "good" : decision.final_decision.includes("open_short") ? "bad" : "neutral"}>
          {label(decision.final_decision)}
        </Badge>
      </View>
      <View style={styles.cardFooter}>
        <Text style={styles.muted}>Score {score ?? "--"} / {label(decision.approval_status)}</Text>
        <Text style={isPositive ? styles.goodText : styles.badText}>{percent(move?.change24h)} 24h</Text>
      </View>
    </Pressable>
  );
}

function TradeCard({ move, onPress, trade }: { trade: TradeRow; move?: MarketMove; onPress: () => void }) {
  const marketMove = move ?? fallbackMoves[normalizeMarketSymbol(trade.symbol)];
  const live = marketMove ? livePnlForTrade(trade, { [normalizeMarketSymbol(trade.symbol)]: marketMove }) : { pnl: 0, pnlPct: 0 };
  const value = isTradeOpen(trade) ? live.pnl : toNumber(trade.realized_pnl);
  const isWinner = value >= 0;
  const isPositiveMove = (move?.change24h ?? 0) >= 0;

  return (
    <Pressable onPress={onPress} style={styles.card}>
      <View style={styles.rowBetween}>
        <View style={styles.cardMain}>
          <Text style={styles.symbol}>{trade.symbol}</Text>
          <Text style={styles.meta}>{label(trade.status)} / {label(trade.lifecycle_status ?? trade.close_reason)} / {minutesAgo(trade.closed_at ?? trade.created_at)} ago</Text>
        </View>
        <View style={styles.alignRight}>
          <Text style={isWinner ? styles.rGood : styles.rBad}>{isTradeOpen(trade) ? currency(value) : rMultiple(trade.r_multiple)}</Text>
          <Text style={isWinner ? styles.goodText : styles.badText}>{isTradeOpen(trade) ? percent(live.pnlPct) : currency(toNumber(trade.realized_pnl))}</Text>
        </View>
      </View>
      <View style={styles.cardFooter}>
        <Text style={styles.muted}>{label(trade.mode)} / entry {formatPrice(entryPrice(trade))}</Text>
        <Text style={isPositiveMove ? styles.goodText : styles.badText}>{percent(move?.change24h)} 24h</Text>
      </View>
    </Pressable>
  );
}

function BotCard({
  bot,
  busy,
  move,
  onAction,
}: {
  bot: BotRow;
  busy: string | null;
  move?: MarketMove;
  onAction: (bot: BotRow, action: BotAction) => void;
}) {
  const isRunning = bot.status === "running" || bot.status === "active";
  const isPositiveMove = (move?.change24h ?? 0) >= 0;

  return (
    <View style={styles.card}>
      <View style={styles.rowBetween}>
        <View style={styles.cardMain}>
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
      <View style={styles.actionWrap}>
        <ActionButton
          disabled={isRunning}
          label="Start"
          busy={busy === `bot-activate-${bot.id}`}
          onPress={() => onAction(bot, "activate")}
        />
        <ActionButton
          disabled={!isRunning}
          label="Pause"
          busy={busy === `bot-pause-${bot.id}`}
          onPress={() => onAction(bot, "pause")}
        />
        <ActionButton
          disabled={false}
          label="Archive"
          busy={busy === `bot-archive-${bot.id}`}
          onPress={() => onAction(bot, "archive")}
          tone="danger"
        />
      </View>
    </View>
  );
}

function DecisionDetail({
  busy,
  decision,
  move,
  onApprove,
  onReject,
  rejectReason,
  setRejectReason,
}: {
  busy: string | null;
  decision: DecisionRow;
  move?: MarketMove;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  rejectReason: string;
  setRejectReason: (value: string) => void;
}) {
  const pending = isPendingManualDecision(decision);

  return (
    <View style={styles.stack}>
      <View style={styles.card}>
        <View style={styles.rowBetween}>
          <Text style={styles.symbol}>{label(decision.final_decision)}</Text>
          <Text style={(move?.change24h ?? 0) >= 0 ? styles.goodText : styles.badText}>{percent(move?.change24h)} 24h</Text>
        </View>
        <View style={styles.detailGrid}>
          <Metric label="Score" value={String(scoreFromSummary(decision.score_summary) ?? "--")} />
          <Metric label="Approval" value={label(decision.approval_status)} />
          <Metric label="Mode" value={label(decision.mode)} />
        </View>
      </View>

      <JsonPanel title="Score summary" data={decision.score_summary} />
      <JsonPanel title="Risk summary" data={decision.risk_summary} />
      <JsonPanel title="Security summary" data={decision.security_summary} />

      {pending ? (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Manual approval</Text>
          <TextInput
            onChangeText={setRejectReason}
            placeholder="Reject reason"
            placeholderTextColor="#71717a"
            style={[styles.input, styles.textArea]}
            value={rejectReason}
            multiline
          />
          <View style={styles.actionRow}>
            <Pressable disabled={busy != null} onPress={() => onApprove(decision.id)} style={styles.primaryButtonSmall}>
              <Text style={styles.primaryButtonText}>{busy === `approve-${decision.id}` ? "Approving..." : "Approve"}</Text>
            </Pressable>
            <Pressable disabled={busy != null} onPress={() => onReject(decision.id)} style={styles.dangerButtonSmall}>
              <Text style={styles.dangerButtonText}>{busy === `reject-${decision.id}` ? "Rejecting..." : "Reject"}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

function TradeDetail({
  actionError,
  busy,
  manualPercent,
  manualPrice,
  manualQuantity,
  manualStop,
  manualTakeProfit,
  move,
  onAction,
  setManualPercent,
  setManualPrice,
  setManualQuantity,
  setManualStop,
  setManualTakeProfit,
  trade,
}: {
  actionError: string | null;
  busy: string | null;
  manualPercent: string;
  manualPrice: string;
  manualQuantity: string;
  manualStop: string;
  manualTakeProfit: string;
  move?: MarketMove;
  onAction: (action: ManualAction) => void;
  setManualPercent: (value: string) => void;
  setManualPrice: (value: string) => void;
  setManualQuantity: (value: string) => void;
  setManualStop: (value: string) => void;
  setManualTakeProfit: (value: string) => void;
  trade: TradeRow;
}) {
  const marketMove = move ?? fallbackMoves[normalizeMarketSymbol(trade.symbol)];
  const live = marketMove ? livePnlForTrade(trade, { [normalizeMarketSymbol(trade.symbol)]: marketMove }) : { pnl: 0, pnlPct: 0 };
  const open = isTradeOpen(trade);
  const tpLevels = getTpLevels(trade);
  const liveLocked = trade.mode === "live";

  return (
    <View style={styles.stack}>
      <View style={styles.card}>
        <View style={styles.rowBetween}>
          <View>
            <Text style={styles.symbol}>{label(trade.direction)} {label(trade.status)}</Text>
            <Text style={styles.meta}>Last {formatPrice(move?.lastPrice)} / Entry {formatPrice(entryPrice(trade))}</Text>
          </View>
          <View style={styles.alignRight}>
            <Text style={live.pnl >= 0 ? styles.goodTextBig : styles.badTextBig}>{open ? currency(live.pnl) : currency(toNumber(trade.realized_pnl))}</Text>
            <Text style={live.pnlPct >= 0 ? styles.goodText : styles.badText}>{open ? percent(live.pnlPct) : rMultiple(trade.r_multiple)}</Text>
          </View>
        </View>
        <View style={styles.detailGrid}>
          <Metric label="Quantity" value={String(trimNumber(quantityForTrade(trade)))} />
          <Metric label="Stop" value={formatPrice(toNumber(trade.stop_loss))} />
          <Metric label="Take profit" value={formatPrice(toNumber(trade.take_profit))} />
        </View>
      </View>

      {tpLevels.length ? (
        <View style={styles.card}>
          <SectionTitle title="Take profit plan" value={`${tpLevels.length} levels`} />
          {tpLevels.map((tp, index) => (
            <View key={`${tp.price}-${index}`} style={styles.tpRow}>
              <Text style={styles.muted}>TP{index + 1}</Text>
              <Text style={styles.symbolSmall}>{formatPrice(tp.price)}</Text>
              <Text style={styles.goodText}>{tp.r ? `${tp.r}R` : "--"} / {tp.size ? `${tp.size}%` : "--"}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <View style={styles.card}>
        <SectionTitle title="Manual trade terminal" value={open ? "active" : "inactive"} />
        {liveLocked ? (
          <Text style={styles.warning}>Live market close/add/reduce stays locked here. Protective levels can be edited.</Text>
        ) : null}
        <View style={styles.formGrid}>
          <Field label="Price" value={manualPrice} onChangeText={setManualPrice} />
          <Field label="Quantity" value={manualQuantity} onChangeText={setManualQuantity} />
          <Field label="Percent" value={manualPercent} onChangeText={setManualPercent} />
          <Field label="Stop" value={manualStop} onChangeText={setManualStop} />
          <Field label="Take profit" value={manualTakeProfit} onChangeText={setManualTakeProfit} />
        </View>
        {actionError ? <Text style={styles.errorText}>{actionError}</Text> : null}
        <View style={styles.actionWrap}>
          <ActionButton disabled={!open || liveLocked} label="Close" busy={busy === "trade-close_full"} onPress={() => onAction("close_full")} tone="danger" />
          <ActionButton disabled={!open || liveLocked} label="Close %" busy={busy === "trade-close_percent"} onPress={() => onAction("close_percent")} tone="danger" />
          <ActionButton disabled={!open || liveLocked} label="Reduce" busy={busy === "trade-reduce_quantity"} onPress={() => onAction("reduce_quantity")} />
          <ActionButton disabled={!open} label="Stop" busy={busy === "trade-set_stop_loss"} onPress={() => onAction("set_stop_loss")} />
          <ActionButton disabled={!open} label="TP" busy={busy === "trade-set_take_profit"} onPress={() => onAction("set_take_profit")} />
          <ActionButton disabled={!open} label="BE stop" busy={busy === "trade-move_stop_to_entry"} onPress={() => onAction("move_stop_to_entry")} />
        </View>
      </View>

      {trade.lifecycle_error ? (
        <View style={styles.card}>
          <Text style={styles.errorText}>{trade.lifecycle_error}</Text>
        </View>
      ) : null}
    </View>
  );
}

function Field({ label: fieldLabel, onChangeText, value }: { label: string; onChangeText: (value: string) => void; value: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.metricLabel}>{fieldLabel}</Text>
      <TextInput keyboardType="decimal-pad" onChangeText={onChangeText} placeholder="0" placeholderTextColor="#71717a" style={styles.input} value={value} />
    </View>
  );
}

function ActionButton({ busy, disabled, label: buttonLabel, onPress, tone }: { busy: boolean; disabled: boolean; label: string; onPress: () => void; tone?: "danger" }) {
  return (
    <Pressable disabled={disabled || busy} onPress={onPress} style={[styles.actionButton, tone === "danger" && styles.actionButtonDanger, disabled && styles.disabledButton]}>
      <Text style={[styles.actionButtonText, tone === "danger" && styles.dangerButtonText]}>{busy ? "..." : buttonLabel}</Text>
    </Pressable>
  );
}

function JsonPanel({ data, title }: { data?: Record<string, unknown> | null; title: string }) {
  if (!data || Object.keys(data).length === 0) return null;
  return (
    <View style={styles.card}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <Text style={styles.jsonText}>{JSON.stringify(data, null, 2)}</Text>
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

function normalizePaperAccount(row: Record<string, unknown> | null): PaperAccount | null {
  if (!row) return null;
  const balance = toNumber(row.balance);
  const reserved = toNumber(row.reserved_balance);
  return {
    starting_balance: toNumber(row.starting_balance ?? balance),
    balance,
    reserved_balance: reserved,
    available_balance: toNumber(row.available_balance ?? balance - reserved),
    realized_pnl: toNumber(row.realized_pnl),
    unrealized_pnl: toNumber(row.unrealized_pnl),
    equity: toNumber(row.equity ?? balance),
    status: String(row.status ?? (row.is_active ? "active" : "inactive")),
  };
}

function exchangeName(account: ExchangeAccount): WalletMode | "" {
  const raw = String(account.exchange ?? "").toLowerCase();
  if (raw.includes("binance")) return "binance";
  if (raw.includes("bybit")) return "bybit";
  if (raw.includes("okx")) return "okx";
  return "";
}

function isPendingManualDecision(decision: DecisionRow) {
  return decision.approval_status === "pending" && (decision.manual_approval_required || decision.final_decision.includes("open_"));
}

function isTradeOpen(trade: TradeRow) {
  return trade.status === "open" && trade.lifecycle_status !== "closed";
}

function moveForTrade(trade: TradeRow, moves: Record<string, MarketMove>) {
  return moves[normalizeMarketSymbol(trade.symbol)];
}

function entryPrice(trade: TradeRow) {
  return toNumber(trade.avg_fill_price ?? trade.avg_entry_price ?? trade.entry_price);
}

function quantityForTrade(trade: TradeRow) {
  return toNumber(trade.filled_quantity ?? trade.quantity);
}

function livePnlForTrade(trade: TradeRow, moves: Record<string, MarketMove>) {
  const price = moveForTrade(trade, moves)?.lastPrice ?? 0;
  const entry = entryPrice(trade);
  const qty = quantityForTrade(trade);
  if (!isTradeOpen(trade) || !price || !entry || !qty) {
    return { pnl: toNumber(trade.unrealized_pnl), pnlPct: toNumber(trade.pnl_pct) };
  }
  const isShort = String(trade.direction ?? "").toLowerCase() === "short";
  const pnl = (isShort ? entry - price : price - entry) * qty;
  const notional = entry * qty;
  return { pnl, pnlPct: notional > 0 ? (pnl / notional) * 100 : 0 };
}

function getTpLevels(trade: TradeRow) {
  const meta = trade.metadata ?? {};
  const rewardPlan = (meta.reward_plan ?? meta.tp_plan ?? meta.take_profit_plan) as Record<string, unknown> | undefined;
  const raw = (Array.isArray(rewardPlan?.take_profits) ? rewardPlan?.take_profits : Array.isArray(meta.take_profits) ? meta.take_profits : []) as Record<string, unknown>[];
  const levels = raw
    .map((item) => ({
      price: toNumber(item.target_price ?? item.price ?? item.take_profit),
      r: toNumber(item.r_multiple ?? item.r),
      size: toNumber(item.size_pct ?? item.percent ?? item.close_pct),
    }))
    .filter((item) => item.price > 0);
  if (levels.length) return levels;
  const single = toNumber(trade.take_profit);
  return single > 0 ? [{ price: single, r: 0, size: 100 }] : [];
}

function parseNumber(value: string) {
  const next = Number(value.replace(",", "."));
  return Number.isFinite(next) && next > 0 ? next : null;
}

function toNumber(value: unknown) {
  const next = Number(value ?? 0);
  return Number.isFinite(next) ? next : 0;
}

function trimNumber(value: number) {
  return Number(value.toFixed(8));
}

function currency(value: number) {
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

function formatPrice(value?: number | null) {
  if (!value) return "--";
  return value.toLocaleString("en-US", { maximumFractionDigits: value > 100 ? 2 : 6 });
}

function formatManualActionError(message: string) {
  if (message.includes("schema cache")) {
    return "Manual trade action RPC is not deployed on Supabase yet.";
  }
  if (message.includes("live close/add/reduce")) {
    return "Live market close/add/reduce is locked. Use protective Stop/TP edits or the audited execution service.";
  }
  return message.replace("manual_trade_action: ", "");
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#07090b" },
  keyboardScreen: { flex: 1 },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 },
  authContent: { flexGrow: 1, justifyContent: "flex-start", padding: 24, paddingTop: 84, paddingBottom: 140 },
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
  logoText: { color: "#ccfbf1", fontSize: 18, fontWeight: "800" },
  logoSmall: {
    width: 42,
    height: 42,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "rgba(94,234,212,0.35)",
    backgroundColor: "rgba(94,234,212,0.1)",
  },
  title: { marginTop: 18, color: "#fafafa", fontSize: 42, fontWeight: "800" },
  subtitle: { marginTop: 10, color: "#a1a1aa", fontSize: 16, lineHeight: 24 },
  authCard: { marginTop: 28, gap: 12 },
  input: {
    minHeight: 48,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(255,255,255,0.05)",
    color: "#fafafa",
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
  },
  textArea: { minHeight: 86, textAlignVertical: "top" },
  primaryButton: { height: 52, borderRadius: 10, alignItems: "center", justifyContent: "center", backgroundColor: "#5eead4" },
  primaryButtonText: { color: "#07100f", fontWeight: "800" },
  warning: { color: "#fbbf24", fontSize: 12, lineHeight: 18 },
  errorText: { color: "#fecdd3", fontSize: 12, lineHeight: 18 },
  content: { padding: 18, paddingBottom: 36 },
  header: { marginTop: 8, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 16 },
  headerCopy: { flex: 1 },
  kicker: { color: "#5eead4", fontSize: 11, fontWeight: "800", letterSpacing: 1.4, textTransform: "uppercase" },
  heading: { marginTop: 4, color: "#fafafa", fontSize: 34, fontWeight: "800" },
  headingSmall: { marginTop: 4, color: "#fafafa", fontSize: 28, fontWeight: "800" },
  ghostButton: { borderRadius: 10, borderWidth: 1, borderColor: "rgba(255,255,255,0.12)", paddingHorizontal: 12, paddingVertical: 10 },
  ghostButtonText: { color: "#e4e4e7", fontWeight: "700" },
  walletWrap: { marginTop: 22, gap: 10 },
  sectionLabel: { color: "#a1a1aa", fontSize: 11, fontWeight: "800", textTransform: "uppercase" },
  walletRow: { flexDirection: "row", gap: 8 },
  walletChip: {
    minWidth: 94,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(255,255,255,0.05)",
    paddingHorizontal: 13,
    paddingVertical: 11,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
  },
  walletChipActive: { backgroundColor: "#f4f4f5", borderColor: "#f4f4f5" },
  walletChipText: { color: "#a1a1aa", fontSize: 12, fontWeight: "800" },
  walletChipTextActive: { color: "#09090b" },
  dot: { width: 7, height: 7, borderRadius: 7 },
  dotGood: { backgroundColor: "#5eead4" },
  dotMuted: { backgroundColor: "#52525b" },
  walletCard: {
    marginTop: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(94,234,212,0.18)",
    backgroundColor: "rgba(20,184,166,0.08)",
    padding: 16,
  },
  walletValue: { marginTop: 8, color: "#fafafa", fontSize: 32, fontWeight: "900" },
  alignRight: { alignItems: "flex-end" },
  summaryGrid: { marginTop: 14, flexDirection: "row", gap: 10 },
  metricCard: {
    flex: 1,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(255,255,255,0.05)",
    padding: 12,
  },
  metricLabel: { color: "#a1a1aa", fontSize: 10, fontWeight: "800", textTransform: "uppercase" },
  metricValue: { marginTop: 7, color: "#fafafa", fontSize: 15, fontWeight: "800" },
  tabs: { marginTop: 18, flexDirection: "row", borderRadius: 10, backgroundColor: "rgba(255,255,255,0.05)", padding: 4 },
  tab: { flex: 1, alignItems: "center", borderRadius: 8, paddingVertical: 10 },
  tabActive: { backgroundColor: "#f4f4f5" },
  tabText: { color: "#a1a1aa", fontSize: 11, fontWeight: "800" },
  tabTextActive: { color: "#09090b" },
  liquidTabs: {
    marginTop: 18,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.14)",
    backgroundColor: "rgba(255,255,255,0.07)",
    padding: 5,
    shadowColor: "#5eead4",
    shadowOpacity: 0.18,
    shadowRadius: 18,
  },
  liquidTabsRow: { flexDirection: "row", gap: 6 },
  liquidTab: {
    minWidth: 88,
    alignItems: "center",
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 11,
    borderWidth: 1,
    borderColor: "transparent",
  },
  liquidTabActive: {
    backgroundColor: "rgba(244,244,245,0.92)",
    borderColor: "rgba(255,255,255,0.72)",
    shadowColor: "#ffffff",
    shadowOpacity: 0.24,
    shadowRadius: 12,
  },
  liquidTabText: { color: "#a1a1aa", fontSize: 11, fontWeight: "900" },
  liquidTabTextActive: { color: "#09090b" },
  stack: { marginTop: 16, gap: 12 },
  sectionHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  sectionTitle: { color: "#fafafa", fontSize: 16, fontWeight: "900" },
  sectionValue: { color: "#5eead4", fontSize: 12, fontWeight: "800" },
  card: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    backgroundColor: "rgba(24,24,27,0.86)",
    padding: 16,
    gap: 12,
  },
  cardMain: { flex: 1 },
  rowBetween: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 14 },
  symbol: { color: "#fafafa", fontSize: 17, fontWeight: "800" },
  symbolSmall: { color: "#fafafa", fontSize: 14, fontWeight: "800" },
  meta: { marginTop: 6, color: "#71717a", fontSize: 12, lineHeight: 18 },
  cardFooter: { marginTop: 4, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  muted: { color: "#a1a1aa", fontSize: 13 },
  goodText: { color: "#a7f3d0", fontSize: 12, fontWeight: "800" },
  badText: { color: "#fecdd3", fontSize: 12, fontWeight: "800" },
  goodTextBig: { color: "#a7f3d0", fontSize: 20, fontWeight: "900" },
  badTextBig: { color: "#fecdd3", fontSize: 20, fontWeight: "900" },
  rGood: { color: "#a7f3d0", fontSize: 22, fontWeight: "900" },
  rBad: { color: "#fecdd3", fontSize: 22, fontWeight: "900" },
  badge: {
    maxWidth: 132,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(125,211,252,0.25)",
    backgroundColor: "rgba(125,211,252,0.1)",
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  goodBadge: { borderColor: "rgba(110,231,183,0.3)", backgroundColor: "rgba(110,231,183,0.1)" },
  badBadge: { borderColor: "rgba(251,113,133,0.3)", backgroundColor: "rgba(251,113,133,0.1)" },
  badgeText: { color: "#bae6fd", fontSize: 10, fontWeight: "900", textAlign: "center" },
  goodBadgeText: { color: "#a7f3d0" },
  badBadgeText: { color: "#fecdd3" },
  detailGrid: { flexDirection: "row", gap: 10 },
  actionRow: { flexDirection: "row", gap: 10 },
  primaryButtonSmall: { flex: 1, borderRadius: 10, alignItems: "center", justifyContent: "center", backgroundColor: "#5eead4", paddingVertical: 13 },
  dangerButtonSmall: { flex: 1, borderRadius: 10, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(251,113,133,0.16)", borderWidth: 1, borderColor: "rgba(251,113,133,0.35)", paddingVertical: 13 },
  dangerButtonFull: { borderRadius: 10, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(251,113,133,0.16)", borderWidth: 1, borderColor: "rgba(251,113,133,0.35)", paddingVertical: 14 },
  dangerButtonText: { color: "#fecdd3", fontWeight: "800" },
  jsonText: { color: "#d4d4d8", fontSize: 12, lineHeight: 18 },
  tpRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 7, borderTopWidth: 1, borderTopColor: "rgba(255,255,255,0.06)" },
  formGrid: { gap: 10 },
  field: { gap: 6 },
  actionWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  actionButton: { minWidth: "30%", flexGrow: 1, borderRadius: 10, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.08)", borderWidth: 1, borderColor: "rgba(255,255,255,0.12)", paddingVertical: 12 },
  actionButtonDanger: { backgroundColor: "rgba(251,113,133,0.14)", borderColor: "rgba(251,113,133,0.3)" },
  actionButtonText: { color: "#fafafa", fontWeight: "800" },
  disabledButton: { opacity: 0.42 },
  ghostButtonWide: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
    paddingHorizontal: 12,
    paddingVertical: 14,
    alignItems: "center",
  },
});
