"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Clock,
  AlertTriangle,
  TrendingDown,
  TrendingUp,
  Minus,
  DollarSign,
  Zap,
  Plus,
  Trash2,
  BarChart3,
  Layers,
  Activity,
} from "lucide-react";
import Navbar from "@/components/Navbar";
import MotionCard from "@/components/MotionCard";
import Badge from "@/components/Badge";

/* ─── Types ─── */

interface GlobalSettings {
  user_wage: string;
  style_multiplier: number;
  is_student: boolean;
  isSet: boolean;
}

interface SubscriptionEntry {
  id: number;
  app_name: string;
  cost: number;
  months_subscribed: number;
  weekly_hours: number[];
}

interface FormData {
  app_name: string;
  cost: string;
  months_subscribed: string;
  w1: string;
  w2: string;
  w3: string;
  w4: string;
}

/* ─── Helpers ─── */

const getActionColor = (action: string | undefined): "safe" | "warn" | "danger" => {
  if (!action) return "warn";
  if (action.includes("KEEP") || action.includes("UPGRADE")) return "safe";
  if (action.includes("CANCEL") || action.includes("DOWNGRADE")) return "danger";
  return "warn";
};

const getVelocityLabel = (velocity: number): string => {
  if (velocity > 1.05) return "↑ INCREASING";
  if (velocity < 0.95) return "↓ DECLINING";
  return "→ STABLE";
};

const getVelocityIcon = (velocity: number) => {
  if (velocity > 1.05) return <TrendingUp className="text-green-600 dark:text-green-400" size={14} />;
  if (velocity < 0.95) return <TrendingDown className="text-red-600 dark:text-red-400" size={14} />;
  return <Minus className="text-muted-foreground" size={14} />;
};

/* ═══════════════════════════════════════════════════════════
   ScreentimeSense Page
   ═══════════════════════════════════════════════════════════ */

export default function ScreentimeSensePage() {
  /* ── State ── */
  const [globalSettings, setGlobalSettings] = useState<GlobalSettings>({
    user_wage: "",
    style_multiplier: 0.1,
    is_student: false,
    isSet: false,
  });

  const [formData, setFormData] = useState<FormData>({
    app_name: "",
    cost: "",
    months_subscribed: "1",
    w1: "",
    w2: "",
    w3: "",
    w4: "",
  });

  const [subscriptions, setSubscriptions] = useState<SubscriptionEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [batchResults, setBatchResults] = useState<any>(null);
  const [expandedResult, setExpandedResult] = useState<number | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  /* ── Event Handlers ── */

  const saveSettings = (e: React.FormEvent) => {
    e.preventDefault();
    if (!globalSettings.user_wage || parseFloat(globalSettings.user_wage) <= 0) return;
    setGlobalSettings((prev) => ({ ...prev, isSet: true }));
  };

  const addSubscription = (e: React.FormEvent) => {
    e.preventDefault();
    const newSub: SubscriptionEntry = {
      id: Date.now(),
      app_name: formData.app_name,
      cost: parseFloat(formData.cost),
      months_subscribed: parseInt(formData.months_subscribed, 10),
      weekly_hours: [
        parseFloat(formData.w1),
        parseFloat(formData.w2),
        parseFloat(formData.w3),
        parseFloat(formData.w4),
      ],
    };
    setSubscriptions((prev) => [...prev, newSub]);
    setFormData({ app_name: "", cost: "", months_subscribed: "1", w1: "", w2: "", w3: "", w4: "" });
  };

  const removeSubscription = (id: number) => {
    setSubscriptions((prev) => prev.filter((s) => s.id !== id));
  };

  const handleAnalyzeBatch = async () => {
    if (subscriptions.length === 0) return;
    setLoading(true);
    setError(null);
    setBatchResults(null);
    setExpandedResult(null);

    try {
      const payload = {
        subscriptions: subscriptions.map((s) => ({
          app_name: s.app_name,
          cost: s.cost,
          months_subscribed: s.months_subscribed,
          weekly_hours: s.weekly_hours,
          user_wage: parseFloat(globalSettings.user_wage),
          style_multiplier: globalSettings.style_multiplier,
        })),
        user_wage: parseFloat(globalSettings.user_wage),
        style_multiplier: globalSettings.style_multiplier,
        is_student: globalSettings.is_student,
      };

      const res = await fetch("/api/screentime/analyze-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Batch analysis failed");
      setBatchResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  const resetAll = () => {
    setBatchResults(null);
    setSubscriptions([]);
    setExpandedResult(null);
    setError(null);
  };

  /* ── Render ── */

  return (
    <>
      <Navbar />
      <main className="max-w-6xl mx-auto px-8 pt-32 pb-12">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-8"
        >
          <h1 className="text-3xl font-bold tracking-tight mb-1.5">
            ScreentimeSense
          </h1>
          <p className="text-muted-foreground">
            Analyze your app usage against personal hourly value to find zombie subscriptions.
          </p>
        </motion.div>

        <AnimatePresence mode="wait">
          {!globalSettings.isSet ? (
            /* ═══════════════════════════════════════════
               STEP 1 — Settings Baseline
               ═══════════════════════════════════════════ */
            <motion.div
              key="settings"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.4 }}
            >
              <MotionCard className="max-w-[28rem] mx-auto" hover={false}>
                <h2 className="text-xl font-bold mb-2">
                  Set Your Baseline
                </h2>
                <p className="text-[0.85rem] text-muted-foreground mb-6">
                  We calculate &quot;Cost Per Hour&quot; (CPH) and compare it against your hourly wage to judge subscription value.
                </p>

                <form onSubmit={saveSettings} className="flex flex-col gap-4">
                  {/* Hourly Wage */}
                  <div>
                    <label className="block text-[0.85rem] font-medium mb-1.5">
                      Your Hourly Wage ($)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="1"
                      required
                      value={globalSettings.user_wage}
                      onChange={(e) => setGlobalSettings({ ...globalSettings, user_wage: e.target.value })}
                      placeholder="20.00"
                      className="w-full"
                    />
                  </div>

                  {/* Budgeting Style — Custom Dropdown */}
                  <div>
                    <label className="block text-[0.85rem] font-medium mb-1.5">
                      Budgeting Style
                    </label>
                    {(() => {
                      const options = [
                        { value: 0.07, label: "Strict (7% wage threshold)" },
                        { value: 0.1, label: "Balanced (10% wage threshold)" },
                        { value: 0.15, label: "Lenient (15% wage threshold)" },
                      ];
                      const selected = options.find((o) => o.value === globalSettings.style_multiplier) || options[1];
                      return (
                        <div className="relative">
                          <button
                            type="button"
                            onClick={() => setDropdownOpen(!dropdownOpen)}
                            className="w-full px-4 py-3 rounded-xl border border-border bg-secondary text-foreground text-sm font-medium text-left cursor-pointer flex items-center justify-between transition-colors focus:border-primary outline-none"
                          >
                            {selected.label}
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className={`opacity-50 transition-transform duration-200 ${dropdownOpen ? "rotate-180" : "rotate-0"}`}>
                              <path d="M4 6L8 10L12 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                            </svg>
                          </button>
                          <AnimatePresence>
                            {dropdownOpen && (
                              <motion.ul
                                initial={{ opacity: 0, y: -6, scale: 0.97 }}
                                animate={{ opacity: 1, y: 4, scale: 1 }}
                                exit={{ opacity: 0, y: -6, scale: 0.97 }}
                                transition={{ duration: 0.18, ease: "easeOut" }}
                                className="absolute top-full left-0 right-0 z-50 list-none m-0 p-1.5 rounded-xl bg-background/95 backdrop-blur-lg border border-border shadow-lg overflow-hidden mt-1"
                              >
                                {options.map((opt) => (
                                  <li
                                    key={opt.value}
                                    onClick={() => {
                                      setGlobalSettings({ ...globalSettings, style_multiplier: opt.value });
                                      setDropdownOpen(false);
                                    }}
                                    className={`px-3.5 py-2.5 rounded-lg text-[0.88rem] cursor-pointer transition-colors ${
                                      opt.value === globalSettings.style_multiplier
                                        ? "text-foreground bg-secondary/80"
                                        : "text-muted-foreground bg-transparent hover:bg-secondary/50 hover:text-foreground"
                                    }`}
                                  >
                                    {opt.label}
                                  </li>
                                ))}
                              </motion.ul>
                            )}
                          </AnimatePresence>
                        </div>
                      );
                    })()}
                  </div>

                  {/* Student Toggle */}
                  <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-secondary">
                    <label className="relative w-11 h-6 inline-block shrink-0">
                      <input
                        type="checkbox"
                        checked={globalSettings.is_student}
                        onChange={(e) => setGlobalSettings({ ...globalSettings, is_student: e.target.checked })}
                        className="opacity-0 w-0 h-0 absolute"
                      />
                      <span
                        className={`absolute cursor-pointer top-0 left-0 right-0 bottom-0 rounded-full transition-colors duration-300 ${
                          globalSettings.is_student ? "bg-cyan-500" : "bg-muted"
                        }`}
                      >
                        <span
                          className={`absolute h-4 w-4 bg-white rounded-full transition-all duration-300 bottom-1 ${
                            globalSettings.is_student ? "left-[1.45rem]" : "left-[0.2rem]"
                          }`}
                        />
                      </span>
                    </label>
                    <div>
                      <span className="text-[0.85rem] font-medium">I&apos;m a Student</span>
                      <p className="text-[0.75rem] text-muted-foreground mt-0.5">
                        Scans Google Calendar for exams &amp; suggests pausing entertainment subscriptions.
                      </p>
                    </div>
                  </div>

                  <button type="submit" className="w-full py-3 mt-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl font-semibold transition-colors shadow-sm">
                    Save Settings &amp; Continue
                  </button>
                </form>
              </MotionCard>
            </motion.div>
          ) : !batchResults ? (
            /* ═══════════════════════════════════════════
               STEP 2 — Subscription Queue
               ═══════════════════════════════════════════ */
            <motion.div
              key="queue"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.4 }}
              className="grid grid-cols-1 md:grid-cols-3 gap-6"
            >
              {/* ── Left: Add Subscription Form ── */}
              <div>
                <MotionCard hover={false}>
                  <div className="flex justify-between items-center pb-4 mb-5 border-b border-border">
                    <h2 className="text-lg font-bold flex items-center gap-2 m-0">
                      <Plus size={18} className="text-cyan-500" /> Add Subscription
                    </h2>
                    <span className="text-xs text-muted-foreground">
                      ${(parseFloat(globalSettings.user_wage || "0") * globalSettings.style_multiplier).toFixed(2)}/hr
                    </span>
                  </div>

                  <form onSubmit={addSubscription} className="flex flex-col gap-5">
                    {/* App Name */}
                    <div>
                      <label className="block text-[0.85rem] font-medium mb-1.5">App Name</label>
                      <input required type="text" placeholder="e.g. Netflix, Duolingo, ChatGPT" value={formData.app_name} onChange={(e) => setFormData({ ...formData, app_name: e.target.value })} className="w-full" />
                    </div>

                    {/* Cost + Months row */}
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-[0.85rem] font-medium mb-1.5">Cost ($)</label>
                        <input required type="number" step="0.01" placeholder="14.99" value={formData.cost} onChange={(e) => setFormData({ ...formData, cost: e.target.value })} className="w-full" />
                      </div>
                      <div>
                        <label className="block text-[0.85rem] font-medium mb-1.5">Months</label>
                        <input required type="number" min="1" value={formData.months_subscribed} onChange={(e) => setFormData({ ...formData, months_subscribed: e.target.value })} className="w-full" />
                      </div>
                    </div>

                    {/* Weekly Hours */}
                    <div>
                      <label className="block text-[0.85rem] font-semibold mb-2">Screen Time (Hours per week)</label>
                      <div className="grid grid-cols-4 gap-4 p-4 rounded-xl bg-secondary">
                        {(
                          [
                            ["Wk 1", "w1"],
                            ["Wk 2", "w2"],
                            ["Wk 3", "w3"],
                            ["Wk 4", "w4"],
                          ] as const
                        ).map(([label, key]) => (
                          <div key={key}>
                            <span className="text-[0.75rem] text-muted-foreground block mb-1">{label}</span>
                            <input
                              required
                              type="number"
                              step="0.1"
                              min="0"
                              placeholder="hrs"
                              className="w-full min-w-[3.5rem] text-center"
                              value={formData[key]}
                              onChange={(e) => setFormData({ ...formData, [key]: e.target.value })}
                            />
                          </div>
                        ))}
                      </div>
                    </div>

                    <button type="submit" className="w-full flex items-center justify-center gap-2 py-3 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl font-semibold transition-colors shadow-sm">
                      <Plus size={16} /> Add to Queue
                    </button>
                  </form>
                </MotionCard>
              </div>

              {/* ── Right: Queue List ── */}
              <div className="md:col-span-2">
                <MotionCard hover={false} className="min-h-[400px]">
                  <div className="flex justify-between items-center pb-4 mb-5 border-b border-border">
                    <h2 className="text-lg font-bold flex items-center gap-2 m-0">
                      <Layers size={18} className="text-cyan-500" /> Subscription Queue
                    </h2>
                    <span className="text-[0.85rem] text-muted-foreground">
                      {subscriptions.length} subscription{subscriptions.length !== 1 ? "s" : ""}
                    </span>
                  </div>

                  {/* Error Banner */}
                  {error && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      className="flex gap-2 items-center px-4 py-3 bg-red-500/10 text-red-600 dark:text-red-400 rounded-xl mb-4 text-[0.85rem]"
                    >
                      <AlertTriangle size={16} />
                      <span>{error}</span>
                    </motion.div>
                  )}

                  {subscriptions.length === 0 ? (
                    /* Empty State */
                    <div className="flex flex-col items-center justify-center py-16 px-8 opacity-40">
                      <Clock size={48} className="text-muted-foreground mb-4" />
                      <p className="text-base font-semibold tracking-wide uppercase text-muted-foreground">No Subscriptions Yet</p>
                      <p className="text-[0.85rem] text-muted-foreground text-center max-w-[18rem] mt-2">
                        Add subscriptions using the form to build your analysis queue.
                      </p>
                    </div>
                  ) : (
                    /* Queue Items + Analyze Button */
                    <div className="flex flex-col gap-3">
                      {subscriptions.map((sub, i) => (
                        <div
                          key={sub.id}
                          className="flex items-center justify-between px-5 py-4 rounded-xl bg-secondary transition-all duration-200"
                        >
                          <div className="flex items-center gap-4">
                            <span className="w-8 h-8 rounded-lg bg-cyan-500/15 text-cyan-600 dark:text-cyan-400 flex items-center justify-center text-[0.8rem] font-bold">
                              {i + 1}
                            </span>
                            <div>
                              <p className="font-semibold text-[0.85rem]">{sub.app_name}</p>
                              <p className="text-[0.75rem] text-muted-foreground mt-0.5">
                                ${sub.cost}/billing • {sub.months_subscribed}mo •{" "}
                                {sub.weekly_hours.reduce((a, b) => a + b, 0).toFixed(1)} hrs total
                              </p>
                            </div>
                          </div>
                          <button
                            onClick={() => removeSubscription(sub.id)}
                            className="bg-transparent border-none p-1.5 text-red-500/60 hover:text-red-500 cursor-pointer transition-colors"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      ))}

                      <button
                        onClick={handleAnalyzeBatch}
                        disabled={loading}
                        className="w-full flex items-center justify-center gap-2 py-3 mt-4 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl font-semibold transition-colors shadow-sm"
                      >
                        {loading ? (
                          <>
                            <Activity size={18} className="animate-spin" /> Querying Gemini AI for {subscriptions.length} subscriptions...
                          </>
                        ) : (
                          <>
                            <Zap size={16} /> Analyze All {subscriptions.length} Subscription{subscriptions.length !== 1 ? "s" : ""}
                          </>
                        )}
                      </button>
                      <p className="text-xs text-muted-foreground text-center mt-1">
                        All {subscriptions.length} Gemini calls fire in parallel — takes ~3 seconds regardless of count.
                      </p>
                    </div>
                  )}
                </MotionCard>
              </div>
            </motion.div>
          ) : (
            /* ═══════════════════════════════════════════
               STEP 3 — Batch Results
               ═══════════════════════════════════════════ */
            <motion.div
              key="results"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="flex flex-col gap-8"
            >
              {/* ── Summary Bar ── */}
              <MotionCard hover={false} className="bg-background">
                <div className="flex flex-wrap justify-between items-center gap-4">
                  <div>
                    <h2 className="text-xl font-bold flex items-center gap-2 mb-1">
                      <BarChart3 size={20} className="text-cyan-500" /> Analysis Complete
                    </h2>
                    <p className="text-[0.85rem] text-muted-foreground">
                      {batchResults.count} subscription{batchResults.count !== 1 ? "s" : ""} analyzed in parallel
                    </p>
                  </div>
                  <div className="flex gap-4 items-center">
                    {batchResults.portfolio?.saturated_categories > 0 && (
                      <div className="text-right pr-4 border-r border-border">
                        <p className="text-xs text-muted-foreground mb-0.5">Portfolio Savings</p>
                        <p className="font-bold text-green-600 dark:text-green-400 text-xl">
                          ${batchResults.portfolio.total_potential_savings_annual.toFixed(2)}/yr
                        </p>
                      </div>
                    )}
                    <button onClick={resetAll} className="text-cyan-600 dark:text-cyan-400 text-[0.85rem] font-semibold bg-transparent border-none cursor-pointer hover:underline">
                      ← New Analysis
                    </button>
                  </div>
                </div>
              </MotionCard>

              {/* ── Portfolio Analysis (Category Saturation) ── */}
              {batchResults.portfolio?.category_insights?.length > 0 && (
                <MotionCard hover={false} delay={0.1} className="border-t-[3px] border-t-yellow-500">
                  <div className="flex items-center gap-2 mb-4 pb-4 border-b border-border">
                    <Layers size={20} className="text-yellow-600 dark:text-yellow-500" />
                    <h3 className="font-bold m-0">Portfolio Analysis — Category Saturation</h3>
                  </div>

                  <div className="flex flex-col gap-6">
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    {batchResults.portfolio.category_insights.map((insight: any, idx: number) => (
                      <motion.div
                        key={idx}
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, delay: 0.15 + idx * 0.1 }}
                        className="p-5 rounded-2xl bg-secondary"
                      >
                        {/* Category Header */}
                        <div className="flex justify-between items-center mb-3">
                          <div className="flex items-center gap-2">
                            <Badge variant="warn" className="text-[0.7rem]">
                              {insight.subscription_count} SUBSCRIPTIONS
                            </Badge>
                            <h4 className="font-bold m-0 capitalize text-lg">{insight.category_label}</h4>
                          </div>
                          <span className="text-[0.9rem] font-bold">
                            ${insight.total_monthly_cost.toFixed(2)}/mo
                          </span>
                        </div>

                        {/* Ranked Subscriptions Table */}
                        <div className="rounded-xl overflow-hidden border border-border bg-background">
                          {/* Table Header */}
                          <div className="grid grid-cols-4 p-3 bg-secondary text-[0.7rem] font-bold uppercase tracking-[0.06em] text-muted-foreground">
                            <span>Rank</span>
                            <span>Subscription</span>
                            <span className="text-right">CPH</span>
                            <span className="text-right">Cost</span>
                          </div>

                          {/* Table Rows — staggered entrance */}
                          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                          {insight.ranked_subscriptions.map((sub: any, rowIdx: number) => (
                            <motion.div
                              key={sub.app_name}
                              initial={{ opacity: 0, x: -8 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ duration: 0.3, delay: 0.25 + idx * 0.1 + rowIdx * 0.08 }}
                              className={`grid grid-cols-4 p-3 items-center border-t border-border ${
                                sub.is_best_value
                                  ? "bg-green-500/10"
                                  : sub.is_worst_value
                                  ? "bg-red-500/10"
                                  : "bg-transparent"
                              }`}
                            >
                              <span
                                className={`text-[0.85rem] font-bold ${
                                  sub.is_best_value
                                    ? "text-green-600 dark:text-green-400"
                                    : sub.is_worst_value
                                    ? "text-red-600 dark:text-red-400"
                                    : "text-inherit"
                                }`}
                              >
                                #{sub.rank} {sub.is_best_value ? "👑" : sub.is_worst_value ? "⚠️" : ""}
                              </span>
                              <span className="text-[0.85rem] font-medium">{sub.app_name}</span>
                              <span
                                className={`text-[0.85rem] text-right font-medium ${
                                  sub.is_best_value
                                    ? "text-green-600 dark:text-green-400"
                                    : sub.is_worst_value
                                    ? "text-red-600 dark:text-red-400"
                                    : "text-inherit"
                                }`}
                              >
                                ${sub.cph.toFixed(2)}/hr
                              </span>
                              <span className="text-[0.85rem] text-right text-muted-foreground">
                                ${sub.monthly_cost.toFixed(2)}/mo
                              </span>
                            </motion.div>
                          ))}
                        </div>

                        {/* Savings Callout Cards */}
                        <div className="flex flex-wrap gap-4 mt-3">
                          <motion.div
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.35, delay: 0.4 + idx * 0.1 }}
                            className="flex-1 min-w-[200px] py-3 px-4 rounded-xl bg-background border border-border"
                          >
                            <p className="text-xs text-muted-foreground mb-1">
                              Drop {insight.worst_value.name}
                            </p>
                            <p className="font-bold text-green-600 dark:text-green-400">
                              ${insight.savings_drop_worst.toFixed(2)}/mo{" "}
                              <span className="text-xs font-medium text-muted-foreground">
                                (${insight.savings_drop_worst_annual.toFixed(2)}/yr)
                              </span>
                            </p>
                          </motion.div>

                          {insight.subscription_count > 2 && (
                            <motion.div
                              initial={{ opacity: 0, y: 8 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ duration: 0.35, delay: 0.5 + idx * 0.1 }}
                              className="flex-1 min-w-[200px] py-3 px-4 rounded-xl bg-background border border-border"
                            >
                              <p className="text-xs text-muted-foreground mb-1">
                                Keep only {insight.best_value.name}
                              </p>
                              <p className="font-bold text-green-600 dark:text-green-400">
                                ${insight.savings_keep_best_only.toFixed(2)}/mo{" "}
                                <span className="text-xs font-medium text-muted-foreground">
                                  (${insight.savings_keep_best_only_annual.toFixed(2)}/yr)
                                </span>
                              </p>
                            </motion.div>
                          )}
                        </div>

                        {/* Recommendation */}
                        <p className="text-[0.78rem] text-muted-foreground mt-3 italic">
                          {insight.recommendation}
                        </p>
                      </motion.div>
                    ))}
                  </div>
                </MotionCard>
              )}

              {/* ── Exam Season Alert ── */}
              {batchResults.exam_alert && batchResults.exam_alert.exam_detected && (
                <motion.div
                  initial={{ opacity: 0, y: -12, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ duration: 0.5, delay: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
                >
                  <MotionCard
                    hover={false}
                    delay={0.25}
                    className="bg-cyan-500/5 border-cyan-500/20"
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-1">
                        {/* Title */}
                        <h3 className="text-base font-bold mb-1">
                          Exam Season Detected
                        </h3>
                        <p className="text-[0.85rem] text-muted-foreground mb-3">
                          {batchResults.exam_alert.message}
                        </p>

                        {/* Upcoming Exams */}
                        {batchResults.exam_alert.exams.length > 0 && (
                          <div className="mb-3">
                            <p className="text-[0.7rem] font-bold uppercase tracking-[0.06em] text-muted-foreground mb-1.5">
                              Upcoming Exams
                            </p>
                            <div className="flex flex-wrap gap-2">
                              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                              {batchResults.exam_alert.exams.map((exam: any, i: number) => (
                                <motion.span
                                  key={i}
                                  initial={{ opacity: 0, scale: 0.9 }}
                                  animate={{ opacity: 1, scale: 1 }}
                                  transition={{ duration: 0.3, delay: 0.35 + i * 0.06 }}
                                  className="text-[0.75rem] font-medium px-2.5 py-1 rounded-lg bg-cyan-500/10 text-cyan-600 dark:text-cyan-400"
                                >
                                  {exam.name} — {exam.date?.slice(0, 10) || "TBD"}
                                </motion.span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Pausable Subscriptions */}
                        {batchResults.exam_alert.pausable_subscriptions.length > 0 && (
                          <div>
                            <p className="text-[0.7rem] font-bold uppercase tracking-[0.06em] text-muted-foreground mb-1.5">
                              Consider Pausing
                            </p>
                            <div className="flex flex-wrap gap-2">
                              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                              {batchResults.exam_alert.pausable_subscriptions.map((sub: any, i: number) => (
                                <motion.span
                                  key={i}
                                  initial={{ opacity: 0, scale: 0.9 }}
                                  animate={{ opacity: 1, scale: 1 }}
                                  transition={{ duration: 0.3, delay: 0.4 + i * 0.06 }}
                                >
                                  <Badge variant="warn" className="text-[0.72rem]">
                                    {sub.name} (${sub.monthly_cost.toFixed(2)}/mo)
                                  </Badge>
                                </motion.span>
                              ))}
                              <motion.span
                                initial={{ opacity: 0, scale: 0.9 }}
                                animate={{ opacity: 1, scale: 1 }}
                                transition={{ duration: 0.3, delay: 0.55 }}
                              >
                                <Badge variant="safe" className="text-[0.72rem] font-bold">
                                  Save ${batchResults.exam_alert.total_monthly_savings.toFixed(2)}/mo
                                </Badge>
                              </motion.span>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </MotionCard>
                </motion.div>
              )}

              {/* ── Individual Results Grid ── */}
              <div>
                <motion.h3
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.3 }}
                  className="font-bold text-lg mb-4"
                >
                  Individual Analysis
                </motion.h3>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  {batchResults.results.map((result: any, i: number) => {
                    const actionVariant = getActionColor(result.action);
                    const borderColor =
                      actionVariant === "safe"
                        ? "border-l-green-500"
                        : actionVariant === "danger"
                        ? "border-l-red-500"
                        : "border-l-yellow-500";
                    const isExpanded = expandedResult === i;
                    const wageThreshold =
                      parseFloat(globalSettings.user_wage || "0") * globalSettings.style_multiplier;

                    return (
                      <motion.div
                        key={i}
                        layout
                        initial={{ opacity: 0, y: 14 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, delay: 0.35 + i * 0.08 }}
                        className={`bg-card text-card-foreground border border-border border-l-[4px] ${borderColor} rounded-2xl p-5 shadow-sm cursor-pointer transition-transform hover:-translate-y-0.5 hover:shadow-md`}
                        onClick={() => setExpandedResult(isExpanded ? null : i)}
                      >
                        {/* Card Header: Name + Action + VRS + CPH */}
                        <div className="flex justify-between items-start">
                          <div>
                            <h4 className="font-bold mb-1">{result.app_name}</h4>
                            <Badge
                              variant={actionVariant}
                              className="text-[0.65rem] font-bold tracking-[0.08em]"
                            >
                              {result.action}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-4">
                            {/* Value Risk Score Circle */}
                            {result.value_risk_score !== undefined && (
                              <div className="text-center">
                                <div
                                  className={`w-12 h-12 rounded-full flex items-center justify-center text-base font-extrabold border-2 ${
                                    result.value_risk_score > 70
                                      ? "bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/50"
                                      : result.value_risk_score >= 40
                                      ? "bg-yellow-500/10 text-yellow-600 dark:text-yellow-500 border-yellow-500/50"
                                      : "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/50"
                                  }`}
                                >
                                  {result.value_risk_score}
                                </div>
                                <p className="text-[0.55rem] text-muted-foreground mt-1 font-semibold uppercase">
                                  VRS
                                </p>
                              </div>
                            )}
                            {/* CPH + Burden */}
                            <div className="text-right">
                              <p
                                className={`text-[0.85rem] font-bold ${
                                  result.math.cph > wageThreshold
                                    ? "text-red-600 dark:text-red-400"
                                    : "text-green-600 dark:text-green-400"
                                }`}
                              >
                                ${result.math.cph.toFixed(2)}/{result.is_presence ? "day" : "hr"}
                              </p>
                              <p className="text-[0.75rem] text-muted-foreground mt-0.5">
                                ${result.math.personal_burden.toFixed(2)}/mo
                              </p>
                            </div>
                          </div>
                        </div>

                        {/* Reason */}
                        <p className="text-[0.78rem] text-muted-foreground mt-2">
                          {result.reason}
                        </p>

                        {/* Velocity Row */}
                        {!result.is_presence && (
                          <div className="flex items-center gap-4 text-[0.75rem] text-muted-foreground mt-3 pt-3 border-t border-border flex-wrap">
                            <span className="flex items-center gap-1">
                              {getVelocityIcon(result.math.velocity)} {result.math.velocity.toFixed(2)}{" "}
                              {getVelocityLabel(result.math.velocity)}
                            </span>
                            <span>
                              {result.math.raw_hours.toFixed(1)} hrs • {result.math.weight}x weight
                            </span>
                            <span>Conf: {result.confidence_label}</span>
                            {result.value_risk_label && (
                              <span
                                className={`font-semibold ${
                                  result.value_risk_score > 70
                                    ? "text-green-600 dark:text-green-400"
                                    : result.value_risk_score >= 40
                                    ? "text-yellow-600 dark:text-yellow-500"
                                    : "text-red-600 dark:text-red-400"
                                }`}
                              >
                                • {result.value_risk_label}
                              </span>
                            )}
                          </div>
                        )}

                        {/* ── Expanded Details ── */}
                        <AnimatePresence>
                          {isExpanded && (
                            <motion.div
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: "auto" }}
                              exit={{ opacity: 0, height: 0 }}
                              transition={{ duration: 0.35, ease: [0.25, 0.1, 0.25, 1] }}
                              className="overflow-hidden"
                            >
                              <div className="mt-4 pt-4 border-t border-border grid grid-cols-1 sm:grid-cols-2 gap-3">
                                {/* Math Breakdown */}
                                <div>
                                  <h5 className="text-[0.7rem] font-bold uppercase tracking-[0.06em] text-muted-foreground mb-2">
                                    Math Breakdown
                                  </h5>
                                  {[
                                    ["Normalized Cost", `$${result.math.normalized_cost.toFixed(2)}/mo`],
                                    ["Household Split", `÷ ${result.math.divisor}`],
                                    ["Personal Burden", `$${result.math.personal_burden.toFixed(2)}/mo`],
                                    ["Effective Hours", `${result.math.eff_hours.toFixed(1)} hrs`],
                                    ["CPH", `$${result.math.cph.toFixed(2)}/${result.is_presence ? "day" : "hr"}`],
                                  ].map(([label, val]) => (
                                    <div
                                      key={label}
                                      className="flex justify-between text-[0.78rem] pb-1.5"
                                    >
                                      <span className="text-muted-foreground">{label}</span>
                                      <span className="font-medium">{val}</span>
                                    </div>
                                  ))}
                                </div>

                                {/* AI Classification */}
                                <div>
                                  <h5 className="text-[0.7rem] font-bold uppercase tracking-[0.06em] text-muted-foreground mb-2">
                                    AI Classification
                                  </h5>
                                  {[
                                    ["Category", result.ai_found_data?.category],
                                    ["Frequency", result.ai_found_data?.frequency],
                                    ["Value Mode", result.ai_found_data?.value_mode?.replace("_", " ")],
                                    ["Free Tier", result.ai_found_data?.has_free_tier ? "Yes" : "No"],
                                    ["Pricing", result.ai_found_data?.pricing_verified ? "✓ Verified" : "⚠ Unverified"],
                                  ].map(([label, val]) => (
                                    <div
                                      key={label}
                                      className="flex justify-between text-[0.78rem] pb-1.5"
                                    >
                                      <span className="text-muted-foreground">{label}</span>
                                      <span className="font-medium capitalize">
                                        {(val as string) || "N/A"}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              </div>

                              {/* Best Plan Optimization */}
                              {result.best_plan && result.ai_found_data?.pricing_verified && (
                                <motion.div
                                  initial={{ opacity: 0, y: 6 }}
                                  animate={{ opacity: 1, y: 0 }}
                                  transition={{ duration: 0.3, delay: 0.1 }}
                                  className="mt-3 p-3 rounded-xl bg-secondary"
                                >
                                  <p className="text-[0.78rem] font-bold mb-1.5">
                                    <DollarSign size={12} className="inline align-middle mr-1" />
                                    Best Plan:{" "}
                                    <span className="capitalize text-yellow-600 dark:text-yellow-500">
                                      {result.best_plan}
                                    </span>
                                  </p>
                                  <div className="flex gap-3 text-[0.75rem] flex-wrap">
                                    {Object.entries(result.breakeven_info?.plan_costs_npv || {}).map(
                                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                                      ([plan, cost]: [string, any]) => (
                                        <span
                                          key={plan}
                                          className={
                                            plan === result.best_plan
                                              ? "font-bold text-foreground"
                                              : "font-normal text-muted-foreground"
                                          }
                                        >
                                          {plan}: ${cost.toFixed(2)}
                                        </span>
                                      )
                                    )}
                                  </div>
                                </motion.div>
                              )}
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </motion.div>
                    );
                  })}
                </div>
              </div>

            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </>
  );
}
