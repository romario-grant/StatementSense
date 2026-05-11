"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle,
  Info,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import Navbar from "@/components/Navbar";
import MotionCard from "@/components/MotionCard";
import Badge from "@/components/Badge";
import {
  readSubscriptionAnalysis,
  subscriptionAnalysisSignature,
} from "@/lib/subscriptionStore";
import { readPageSession, savePageSession } from "@/lib/pageSessionStore";
import { readUserPreferences } from "@/lib/userPreferenceStore";

const FALLBACK_BACKEND_URL =
  "https://statementsense-backend-430268251728.us-central1.run.app";
const PLAN_SIMULATOR_TIMEOUT_MS = 90_000;

type SavedSubscriptionAnalysis = {
  transactions?: Record<string, unknown>[];
  subscriptions?: Record<string, unknown>[];
  price_changes?: Record<string, unknown>[];
  transactions_parsed?: number;
  currency_summary?: {
    exchange_rate?: number;
    exchange_rate_source?: string;
    original_currency?: string;
  };
};

type PlanSimulatorState = {
  loading?: boolean;
  error?: string | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data?: any;
  selectedIndex?: number;
};

type RenewalSession = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  results: any;
  sourceSignature?: string;
  hasSourceAnalysis: boolean;
  exchangeRate: number | null;
  exchangeRateSource: string | null;
  localCurrency: string;
  planSimulators: Record<string, PlanSimulatorState>;
};

type ManualSalary = {
  amount: string;
  payDay: string;
  frequency: "monthly" | "biweekly";
};

export default function RenewalSensePage() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [results, setResults] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [needsManualSalary, setNeedsManualSalary] = useState(false);
  const [manualSalary, setManualSalary] = useState<ManualSalary>({
    amount: "",
    payDay: "",
    frequency: "monthly",
  });
  const [hasSourceAnalysis, setHasSourceAnalysis] = useState(false);
  const [currentMonth] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
  });
  const [exchangeRate, setExchangeRate] = useState<number | null>(null);
  const [exchangeRateSource, setExchangeRateSource] = useState<string | null>(null);
  const [localCurrency, setLocalCurrency] = useState("JMD");
  const [planSimulators, setPlanSimulators] = useState<Record<string, PlanSimulatorState>>({});
  const [sourceSignature, setSourceSignature] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [monthlySubscriptionCapJmd] = useState(
    () => readUserPreferences()?.monthlySubscriptionCapJmd || null
  );
  const autoPlanCompareStarted = useRef(false);
  const activePlanSimulatorKeys = useRef(new Set<string>());

  const runRenewalAnalysis = useCallback(
    async (source: SavedSubscriptionAnalysis, salaryOverride?: ManualSalary) => {
      setLoading(true);
      setError(null);
      setNeedsManualSalary(false);

      const apiBase =
        process.env.NODE_ENV === "production"
          ? (process.env.NEXT_PUBLIC_BACKEND_URL || FALLBACK_BACKEND_URL).replace(
              /\/$/,
              ""
            )
          : "";

      const manualSalaryPayload = salaryOverride
        ? {
            amount: Number(salaryOverride.amount),
            pay_day: Number(salaryOverride.payDay),
            frequency: salaryOverride.frequency,
          }
        : undefined;

      try {
        const response = await fetch(`${apiBase}/api/renewal/analyze-existing`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            transactions: source.transactions || [],
            subscriptions: source.subscriptions || [],
            price_changes: source.price_changes || [],
            manual_salary: manualSalaryPayload,
            year: currentMonth.year,
            month: currentMonth.month,
          }),
        });
        const data = await response.json();
        if (!response.ok) {
          const detail = data.detail && typeof data.detail === "object" ? data.detail : data;
          if (detail.code === "salary_required") {
            setNeedsManualSalary(true);
            throw new Error(
              detail.error || "Enter your pay amount and payday to continue."
            );
          }
          throw new Error(data.detail || data.error || "Renewal analysis failed.");
        }
        autoPlanCompareStarted.current = false;
        setPlanSimulators({});
        activePlanSimulatorKeys.current.clear();
        setResults(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "An error occurred");
      } finally {
        setLoading(false);
      }
    },
    [currentMonth.month, currentMonth.year]
  );

  useEffect(() => {
    const source = readSubscriptionAnalysis<SavedSubscriptionAnalysis>();
    const nextSourceSignature = subscriptionAnalysisSignature(source);
    const saved = readPageSession<RenewalSession>("renewal");
    if (saved?.results && saved.sourceSignature === nextSourceSignature) {
      // Restore the completed RenewalSense workflow when returning to the page.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setResults(saved.results);
      setSourceSignature(saved.sourceSignature || nextSourceSignature);
      setHasSourceAnalysis(saved.hasSourceAnalysis);
      setExchangeRate(saved.exchangeRate);
      setExchangeRateSource(saved.exchangeRateSource);
      setLocalCurrency(saved.localCurrency);
      setPlanSimulators(saved.planSimulators || {});
      setLoading(false);
      setHydrated(true);
      return;
    }

    if (!source?.transactions?.length) {
      // Load the saved browser handoff once when RenewalSense opens.
      setHasSourceAnalysis(false);
      setLoading(false);
      setHydrated(true);
      return;
    }

    setHasSourceAnalysis(true);
    setSourceSignature(nextSourceSignature);
    void runRenewalAnalysis(source);
    setExchangeRate(source.currency_summary?.exchange_rate || null);
    setExchangeRateSource(source.currency_summary?.exchange_rate_source || null);
    setLocalCurrency(source.currency_summary?.original_currency || "JMD");
    setHydrated(true);
  }, [runRenewalAnalysis]);

  useEffect(() => {
    if (!hydrated || !results) return;
    savePageSession("renewal", {
      results,
      sourceSignature,
      hasSourceAnalysis,
      exchangeRate,
      exchangeRateSource,
      localCurrency,
      planSimulators,
    });
  }, [exchangeRate, exchangeRateSource, hasSourceAnalysis, hydrated, localCurrency, planSimulators, results, sourceSignature]);

  const handleManualSalarySubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const amount = Number(manualSalary.amount);
    const payDay = Number(manualSalary.payDay);
    if (
      !Number.isFinite(amount) ||
      amount <= 0 ||
      !Number.isFinite(payDay) ||
      payDay < 1 ||
      payDay > 30
    ) {
      setError("Enter a pay amount and a payday from 1 to 30.");
      setNeedsManualSalary(true);
      return;
    }

    const source = readSubscriptionAnalysis<SavedSubscriptionAnalysis>();
    if (!source?.transactions?.length) {
      setError("Run SubscriptionSense first so RenewalSense can reuse the parsed transactions.");
      return;
    }
    void runRenewalAnalysis(source, manualSalary);
  };

  const apiBase =
    process.env.NODE_ENV === "production"
      ? (process.env.NEXT_PUBLIC_BACKEND_URL || FALLBACK_BACKEND_URL).replace(
          /\/$/,
          ""
        )
      : "";

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const loadPlanSimulator = useCallback(async (sub: any, key: string, force = false) => {
    if (!force && (activePlanSimulatorKeys.current.has(key) || planSimulators[key]?.loading || planSimulators[key]?.data)) {
      return;
    }

    let timeoutId: number | null = null;
    activePlanSimulatorKeys.current.add(key);
    setPlanSimulators((current) => ({
      ...current,
      [key]: {
        loading: true,
        error: null,
        data: current[key]?.data,
        selectedIndex: current[key]?.selectedIndex || 0,
      },
    }));
    try {
      const controller = new AbortController();
      timeoutId = window.setTimeout(() => controller.abort(), PLAN_SIMULATOR_TIMEOUT_MS);
      const response = await fetch(`${apiBase}/api/renewal/plan-simulator`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          subscription: sub,
          salary: results.salary,
          expenses: results.expenses || [],
          transactions: results.transactions || [],
          year: currentMonth.year,
          month: currentMonth.month,
          exchange_rate: exchangeRate,
          exchange_rate_source: exchangeRateSource,
          country: localCurrency === "JMD" ? "Jamaica" : "United States",
          local_currency: localCurrency,
        }),
      });
      const raw = await response.text();
      let data: { detail?: string; error?: string; [key: string]: unknown } = {};
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch {
        throw new Error(raw || `Plan comparison failed with status ${response.status}.`);
      }
      if (!response.ok) {
        throw new Error(data.detail || data.error || "Plan comparison failed.");
      }
      setPlanSimulators((current) => ({
        ...current,
        [key]: { loading: false, error: null, data, selectedIndex: 0 },
      }));
    } catch (err) {
      const message =
        err instanceof DOMException && err.name === "AbortError"
          ? "Plan comparison took too long. Try again in a moment."
          : err instanceof Error
            ? err.message
            : "Plan comparison failed.";
      setPlanSimulators((current) => ({
        ...current,
        [key]: {
          loading: false,
          error: message,
        },
      }));
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId);
      activePlanSimulatorKeys.current.delete(key);
    }
  }, [
    apiBase,
    currentMonth.month,
    currentMonth.year,
    exchangeRate,
    exchangeRateSource,
    localCurrency,
    planSimulators,
    results,
  ]);

  useEffect(() => {
    if (!hydrated || loading || !results?.subscriptions?.length || autoPlanCompareStarted.current) {
      return;
    }

    autoPlanCompareStarted.current = true;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    results.subscriptions.forEach((sub: any, idx: number) => {
      const key = `${sub.subscription}-${idx}`;
      void loadPlanSimulator(sub, key);
    });
  }, [hydrated, loadPlanSimulator, loading, results]);

  const selectPlan = (key: string, selectedIndex: number) => {
    setPlanSimulators((current) => ({
      ...current,
      [key]: { ...current[key], selectedIndex },
    }));
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const getDay = (day: any) => day.day as number;

  const projectedCurrentMonthSubscriptions = results
    ? (results.subscriptions || []).reduce(
        (total: number, sub: { renewal_day?: number; amount?: number }) => {
          const renewalDay = Number(sub.renewal_day || 0);
          const amount = Number(sub.amount || 0);
          const daysInMonth = Number(results.calendar?.days_in_month || 31);
          return renewalDay > 0 && renewalDay <= daysInMonth ? total + amount : total;
        },
        0
      )
    : 0;
  const budgetRatio =
    monthlySubscriptionCapJmd && monthlySubscriptionCapJmd > 0
      ? projectedCurrentMonthSubscriptions / monthlySubscriptionCapJmd
      : 0;
  const budgetStatus =
    !monthlySubscriptionCapJmd
      ? null
      : budgetRatio >= 1
        ? {
            label: "Over cap",
            className: "text-red-600 dark:text-red-400",
            message: "Projected renewals exceed your monthly subscription cap.",
          }
        : budgetRatio >= 0.8
          ? {
              label: "Approaching cap",
              className: "text-yellow-600 dark:text-yellow-500",
              message: "Projected renewals are close to your monthly subscription cap.",
            }
          : {
              label: "Within budget",
              className: "text-green-600 dark:text-green-400",
              message: "Projected renewals are within your monthly subscription cap.",
            };

  return (
    <>
      <Navbar />
      <main className="max-w-6xl mx-auto px-8 pt-32 pb-12">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-8"
        >
          <h1 className="font-light text-4xl md:text-5xl tracking-tighter leading-tight mb-2">
            RenewalSense
          </h1>
          <p className="text-muted-foreground">
            Predict subscription renewal failures using your latest SubscriptionSense analysis.
          </p>
        </motion.div>

        <AnimatePresence mode="wait">
          {loading ? (
            <motion.div
              key="loading"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              className="max-w-lg mx-auto"
            >
              <MotionCard hover={false} className="text-center py-12">
                <Loader2 size={34} className="animate-spin mx-auto mb-4 text-muted-foreground" />
                <h2 className="text-lg font-medium mb-2">Building Renewal Insights</h2>
                <p className="text-sm text-muted-foreground">
                  Reusing your parsed transactions and detected subscriptions.
                </p>
              </MotionCard>
            </motion.div>
          ) : !hasSourceAnalysis ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              className="max-w-lg mx-auto"
            >
              <MotionCard hover={false} className="text-center py-12">
                <Info size={40} className="text-muted-foreground mx-auto mb-4" />
                <h2 className="text-lg font-medium mb-2">Run SubscriptionSense First</h2>
                <p className="text-sm text-muted-foreground mb-6">
                  RenewalSense now uses the statement data already parsed by SubscriptionSense, so you only upload once.
                </p>
                <a
                  href="/subscription"
                  className="inline-flex items-center justify-center rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                >
                  Go to SubscriptionSense
                </a>
              </MotionCard>
            </motion.div>
          ) : error ? (
            <motion.div
              key="error"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              className="max-w-lg mx-auto"
            >
              <MotionCard hover={false} className="text-center py-12">
                <AlertTriangle size={40} className="text-red-600 dark:text-red-400 mx-auto mb-4" />
                <h2 className="text-lg font-medium mb-2">
                  {needsManualSalary ? "Add Pay Cycle" : "Could Not Build Renewal Insights"}
                </h2>
                <p className="text-sm text-muted-foreground mb-6">{error}</p>
                {needsManualSalary ? (
                  <form onSubmit={handleManualSalarySubmit} className="space-y-4 text-left">
                    <label className="block text-sm font-medium">
                      Pay amount
                      <input
                        type="number"
                        min="0.01"
                        step="0.01"
                        value={manualSalary.amount}
                        onChange={(event) =>
                          setManualSalary((current) => ({
                            ...current,
                            amount: event.target.value,
                          }))
                        }
                        placeholder="150000"
                        className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                      />
                    </label>
                    <label className="block text-sm font-medium">
                      Payday
                      <input
                        type="number"
                        min="1"
                        max="30"
                        step="1"
                        value={manualSalary.payDay}
                        onChange={(event) =>
                          setManualSalary((current) => ({
                            ...current,
                            payDay: event.target.value,
                          }))
                        }
                        placeholder="25"
                        className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                      />
                    </label>
                    <label className="block text-sm font-medium">
                      Pay cycle
                      <select
                        value={manualSalary.frequency}
                        onChange={(event) =>
                          setManualSalary((current) => ({
                            ...current,
                            frequency: event.target.value as ManualSalary["frequency"],
                          }))
                        }
                        className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                      >
                        <option value="monthly">Monthly</option>
                        <option value="biweekly">Biweekly</option>
                      </select>
                    </label>
                    <button
                      type="submit"
                      className="inline-flex w-full items-center justify-center rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                    >
                      Recalculate RenewalSense
                    </button>
                  </form>
                ) : (
                  <a
                    href="/subscription"
                    className="inline-flex items-center justify-center rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                  >
                    Refresh in SubscriptionSense
                  </a>
                )}
              </MotionCard>
            </motion.div>
          ) : (
            <motion.div
              key="results"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="grid grid-cols-1 md:grid-cols-3 gap-6"
            >
              <div className="flex flex-col gap-6">
                <MotionCard hover={false} delay={0}>
                  <h3 className="font-medium mb-4 text-[0.95rem]">Analysis Summary</h3>
                  {[
                    ["Transactions Reused", results.transactions_parsed],
                    [
                      "Monthly Income",
                      `$${results.salary.amount.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                      })}`,
                      "text-green-600 dark:text-green-400",
                    ],
                    ["Payday", `Day ${results.salary.pay_day}`],
                    ["Total Subscriptions", results.summary.total_subscriptions],
                    [
                      "Monthly Subs Cost",
                      `$${results.summary.total_sub_cost.toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                      })}`,
                      "text-yellow-600 dark:text-yellow-500",
                    ],
                  ].map(([label, value, colorClass], i) => (
                    <div
                      key={i}
                      className="flex justify-between items-center py-2.5 border-b border-border text-[0.88rem] last:border-0"
                    >
                      <span className="text-muted-foreground">{label}</span>
                      <span className={`font-medium ${colorClass || "text-foreground"}`}>
                        {value}
                      </span>
                    </div>
                  ))}
                </MotionCard>

                {budgetStatus && monthlySubscriptionCapJmd && (
                  <MotionCard hover={false} delay={0.05}>
                    <h3 className="font-medium mb-4 text-[0.95rem]">
                      Subscription Budget
                    </h3>
                    {[
                      [
                        "Projected This Month",
                        `JMD $${projectedCurrentMonthSubscriptions.toLocaleString(
                          undefined,
                          { minimumFractionDigits: 2 }
                        )}`,
                      ],
                      [
                        "Monthly Cap",
                        `JMD $${monthlySubscriptionCapJmd.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                        })}`,
                      ],
                      ["Status", budgetStatus.label, budgetStatus.className],
                    ].map(([label, value, colorClass], i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between border-b border-border py-2.5 text-[0.88rem] last:border-0"
                      >
                        <span className="text-muted-foreground">{label}</span>
                        <span className={`font-medium ${colorClass || "text-foreground"}`}>
                          {value}
                        </span>
                      </div>
                    ))}
                    <p className="mt-3 text-xs text-muted-foreground">
                      {budgetStatus.message}
                    </p>
                  </MotionCard>
                )}

                <MotionCard hover={false} delay={0.1}>
                  <h3 className="font-medium mb-1 text-[0.95rem] flex items-center gap-2">
                    <CalendarDays size={16} />
                    {results.calendar.month_name} {results.calendar.year}
                  </h3>
                  <p className="text-xs text-muted-foreground mb-4">
                    Payday is marked on Day {results.salary.pay_day}. Renewals appear by initial.
                  </p>
                  <div className="grid grid-cols-7 gap-1.5 text-center text-[0.65rem] text-muted-foreground mb-2">
                    {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => (
                      <span key={day}>{day}</span>
                    ))}
                  </div>
                  <div className="grid grid-cols-7 gap-1.5">
                    {Array.from({ length: results.calendar.first_weekday }).map((_, idx) => (
                      <div key={`blank-${idx}`} className="aspect-square" />
                    ))}
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    {results.paycycle_map.map((day: any) => {
                      const zoneAccent =
                        day.zone === "safe"
                          ? "bg-green-500"
                          : day.zone === "moderate"
                            ? "bg-yellow-500"
                            : day.zone === "high"
                              ? "bg-orange-500"
                              : "bg-red-500";
                      const isBest = results.start_day_advice?.best_day?.day === getDay(day);
                      return (
                        <div
                          key={day.day}
                          title={`${day.date}: ${day.zone.toUpperCase()} renewal timing risk${day.renewals?.length ? `, ${day.renewals.join(", ")}` : ""}`}
                          className={`relative aspect-square rounded-lg border bg-secondary/60 text-foreground flex items-center justify-center text-[0.75rem] font-medium ${day.is_today ? "border-foreground/40" : "border-border"} ${isBest ? "ring-2 ring-green-500/40" : ""}`}
                        >
                          <span className={`absolute inset-x-1 top-1 h-1 rounded-full ${zoneAccent}`} />
                          <span className="absolute left-1.5 top-2 text-[0.58rem] text-muted-foreground">
                            {day.day}
                          </span>
                          {day.is_payday && (
                            <span className="absolute -top-2 right-0 rounded bg-background px-1 text-[0.5rem] text-foreground border border-border shadow-sm">
                              PAY
                            </span>
                          )}
                          {day.renewals?.length > 0 && (
                            <span className="text-sm font-semibold">{day.renewals[0].substring(0, 1)}</span>
                          )}
                          {isBest && (
                            <span className="absolute bottom-1 right-1 h-1.5 w-1.5 rounded-full bg-green-500" />
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 mt-3 text-[0.7rem] text-muted-foreground">
                    <span className="font-medium text-foreground">Renewal timing risk:</span>
                    {[
                      ["Low risk", "bg-green-500"],
                      ["Moderate risk", "bg-yellow-500"],
                      ["High risk", "bg-orange-500"],
                      ["Critical risk", "bg-red-500"],
                    ].map(([label, colorClass]) => (
                      <div key={label} className="flex items-center gap-1">
                        <span className={`w-2.5 h-2.5 rounded-sm ${colorClass}`} />
                        {label}
                      </div>
                    ))}
                  </div>
                </MotionCard>

                {results.start_day_advice?.best_day && (
                  <MotionCard hover={false} delay={0.12} className="border-border bg-background">
                    <h3 className="font-medium mb-2 text-[0.95rem]">
                      Best Day To Start A New Subscription
                    </h3>
                    <p className="text-2xl font-medium text-green-600 dark:text-green-400 mb-1">
                      {results.calendar.month_name} {results.start_day_advice.best_day.day}
                    </p>
                    <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
                      This day has the lowest estimated payment risk based on your payday,
                      nearby spending, and existing renewals. It is{" "}
                      {results.start_day_advice.best_day.days_since_payday} day(s) after payday,
                      with ${results.start_day_advice.best_day.cluster_amount.toLocaleString()} in nearby spending
                      and {results.start_day_advice.best_day.collision_count} existing renewal(s).
                    </p>
                    <p className="text-[0.7rem] font-medium text-muted-foreground mb-2">
                      Other low-risk options
                    </p>
                    <div className="flex flex-wrap gap-2 text-xs">
                      {results.start_day_advice.alternatives.map(
                        // eslint-disable-next-line @typescript-eslint/no-explicit-any
                        (day: any) => (
                          <span key={day.day} className="rounded-full bg-background px-2 py-1 border border-border">
                            Day {day.day}
                          </span>
                        )
                      )}
                    </div>
                  </MotionCard>
                )}

                <a
                  href="/subscription"
                  className="w-full py-2.5 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-xl text-sm font-medium transition-colors border border-border text-center"
                >
                  Refresh in SubscriptionSense
                </a>
              </div>

              <div className="flex flex-col gap-6 md:col-span-2">
                {results.renewal_predictions && results.renewal_predictions.length > 0 && (
                  <MotionCard hover={false} delay={0.15} className="border-border bg-secondary">
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="text-lg font-medium m-0 flex items-center gap-2">
                        <RefreshCw size={18} />
                        Upcoming Charges
                      </h2>
                      <Badge variant="info">PREDICTED</Badge>
                    </div>
                    <div className="flex flex-col gap-3">
                      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                      {results.renewal_predictions.map((pred: any, idx: number) => {
                        const urgencyColor =
                          pred.days_until_charge <= 3
                            ? "text-red-600 dark:text-red-400"
                            : pred.days_until_charge <= 7
                              ? "text-yellow-600 dark:text-yellow-500"
                              : "text-green-600 dark:text-green-400";
                        const confVariant =
                          pred.confidence_label === "high"
                            ? "safe"
                            : pred.confidence_label === "medium"
                              ? "warn"
                              : "danger";
                        return (
                          <div key={idx} className="flex items-center gap-4 px-4 py-3.5 rounded-xl bg-background border border-border">
                            <div className="text-center min-w-[3.5rem]">
                              <p className={`text-2xl font-medium leading-none ${urgencyColor}`}>
                                {pred.days_until_charge}
                              </p>
                              <p className="text-[0.65rem] text-muted-foreground mt-0.5">
                                days
                              </p>
                            </div>
                            <div className="flex-1">
                              <p className="font-medium text-sm">{pred.subscription}</p>
                              <p className="text-xs text-muted-foreground mt-0.5">
                                Next: <span className="font-medium text-foreground">{pred.next_charge_date}</span>
                                <span className="mx-1.5 opacity-30">|</span>
                                Window: {pred.confidence_window.earliest} - {pred.confidence_window.latest}
                              </p>
                            </div>
                            <div className="text-right">
                              <Badge variant={confVariant as "safe" | "warn" | "danger"} className="capitalize">
                                {pred.confidence_label}
                              </Badge>
                              <p className="text-[0.7rem] text-muted-foreground mt-1">
                                {pred.data_points} data pt{pred.data_points !== 1 ? "s" : ""}
                              </p>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </MotionCard>
                )}

                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2 }}
                >
                  <h2 className="text-xl font-medium pb-3 border-b border-border mb-4">
                    Subscription Risk Report
                  </h2>
                </motion.div>

                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {results.subscriptions.map((sub: any, idx: number) => {
                  const riskColor =
                    sub.risk_level === "low"
                      ? "border-l-green-500"
                      : sub.risk_level === "moderate"
                        ? "border-l-yellow-500"
                        : "border-l-red-500";
                  const riskVariant =
                    sub.risk_level === "low"
                      ? "safe"
                      : sub.risk_level === "moderate"
                        ? "warn"
                        : "danger";
                  return (
                    <MotionCard
                      key={idx}
                      delay={0.1 * idx + 0.25}
                      hover={false}
                      className={`border-l-[3px] ${riskColor}`}
                    >
                      <div className="flex justify-between items-start mb-3">
                        <div>
                          <h3 className="text-base font-medium flex items-center gap-2 mb-1">
                            {sub.subscription}
                            <Badge variant={riskVariant as "safe" | "warn" | "danger"}>
                              {sub.risk_label.toUpperCase()} RISK ({Math.round(sub.risk_score * 100)}%)
                            </Badge>
                          </h3>
                          <p className="text-sm text-muted-foreground">
                            Renews on Day {sub.renewal_day}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-xl font-medium text-yellow-600 dark:text-yellow-500">
                            ${sub.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                          </p>
                          <p className="text-xs text-muted-foreground">per month</p>
                        </div>
                      </div>

                      <div className="p-3 rounded-lg bg-secondary mb-3">
                        <p className="flex items-start gap-2 text-sm font-medium">
                          {sub.risk_level === "low" ? (
                            <CheckCircle size={16} className="text-green-600 dark:text-green-400 shrink-0 mt-0.5" />
                          ) : (
                            <AlertTriangle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
                          )}
                          {sub.advice}
                        </p>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-[0.82rem]">
                        {[
                          ["Paycycle Position", `${sub.breakdown.days_since_payday} days after payday`],
                          ["Subscription Load", `${Math.round(sub.breakdown.subscription_load_factor * 100)}% of salary`],
                          ["Nearby Spending", `$${sub.breakdown.nearby_spend.toLocaleString()} within +/-3 days`],
                          ["Spent Before Renewal", `${Math.round(sub.breakdown.spend_before_factor * 100)}% of salary`],
                          ["Payment Pattern", `${sub.fail_history} irregular cycles`],
                        ].map(([label, val], i) => (
                          <div key={i} className="flex justify-between pb-1.5 border-b border-border">
                            <span className="text-muted-foreground">{label}</span>
                            <span className="font-medium">{val}</span>
                          </div>
                        ))}
                      </div>

                      <div className="mt-4 border-t border-border pt-4">
                        <button
                          type="button"
                          onClick={() => loadPlanSimulator(sub, `${sub.subscription}-${idx}`, true)}
                          disabled={planSimulators[`${sub.subscription}-${idx}`]?.loading}
                          className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-secondary disabled:opacity-60"
                        >
                          {planSimulators[`${sub.subscription}-${idx}`]?.loading ? (
                            <>
                              <Loader2 size={15} className="animate-spin" />
                              Comparing plans...
                            </>
                          ) : (
                            <>
                              <Sparkles size={15} />
                              {planSimulators[`${sub.subscription}-${idx}`]?.data
                                ? "Refresh Plans"
                                : "Compare Plans"}
                            </>
                          )}
                        </button>

                        {planSimulators[`${sub.subscription}-${idx}`]?.error && (
                          <p className="mt-3 text-sm text-red-600 dark:text-red-400">
                            {planSimulators[`${sub.subscription}-${idx}`]?.error}
                          </p>
                        )}

                        {planSimulators[`${sub.subscription}-${idx}`]?.data && (
                          <div className="mt-4 rounded-xl bg-secondary p-4">
                            {(() => {
                              const key = `${sub.subscription}-${idx}`;
                              const simulator = planSimulators[key];
                              const data = simulator.data;
                              if (!data.pricing_verified) {
                                return (
                                  <p className="text-sm text-muted-foreground">
                                    {data.message || "Verified plan prices were not found."}
                                  </p>
                                );
                              }
                              const selected =
                                data.simulations[simulator.selectedIndex || 0] || data.simulations[0];
                              return (
                                <>
                                  <div className="flex flex-wrap gap-2 mb-4">
                                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                                    {data.simulations.map((item: any, planIdx: number) => (
                                      <button
                                        key={`${item.plan.name}-${planIdx}`}
                                        type="button"
                                        onClick={() => selectPlan(key, planIdx)}
                                        className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                                          (simulator.selectedIndex || 0) === planIdx
                                            ? "border-primary bg-primary text-primary-foreground"
                                            : "border-border bg-background hover:bg-card"
                                        }`}
                                      >
                                        {item.plan.name}
                                      </button>
                                    ))}
                                  </div>
                                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
                                    <div>
                                      <p className="text-xs text-muted-foreground">Plan Cost</p>
                                      <p className="font-medium">
                                        JMD ${selected.plan.amount_jmd.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                      </p>
                                      <p className="text-[0.7rem] text-muted-foreground">
                                        {selected.plan.billing_period}
                                      </p>
                                    </div>
                                    <div>
                                      <p className="text-xs text-muted-foreground">Monthly Change</p>
                                      <p className={`font-medium ${selected.delta_jmd > 0 ? "text-red-600 dark:text-red-400" : "text-green-600 dark:text-green-400"}`}>
                                        {selected.delta_jmd > 0 ? "+" : ""}JMD ${selected.delta_jmd.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                      </p>
                                    </div>
                                    <div>
                                      <p className="text-xs text-muted-foreground">New Risk</p>
                                      <p className="font-medium">{selected.risk.risk_label}</p>
                                    </div>
                                  </div>
                                  <p className="mt-3 text-xs text-muted-foreground">
                                    You are on the {data.likely_current_plan.name} plan.
                                  </p>
                                </>
                              );
                            })()}
                          </div>
                        )}
                      </div>
                    </MotionCard>
                  );
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </>
  );
}
