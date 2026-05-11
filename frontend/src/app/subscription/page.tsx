"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  Info,
  TrendingUp,
  TrendingDown,
  Calendar,
  Check,
  RefreshCw,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import Navbar from "@/components/Navbar";
import MotionCard from "@/components/MotionCard";
import Badge from "@/components/Badge";
import FileUpload from "@/components/FileUpload";
import {
  clearSubscriptionAnalysis,
  readSharedSubscriptions,
  readSubscriptionAnalysis,
  saveSharedSubscriptions,
  saveSubscriptionAnalysis,
} from "@/lib/subscriptionStore";
import {
  BUDGETING_STYLES,
  DEFAULT_USER_PREFERENCES,
  type BudgetingStyle,
  type UserPreferences,
  readUserPreferences,
  saveUserPreferences,
} from "@/lib/userPreferenceStore";

const FALLBACK_BACKEND_URL =
  "https://statementsense-backend-430268251728.us-central1.run.app";
const UPLOAD_TIMEOUT_MS = 180_000;

type SubscriptionResult = {
  merchant: string;
  raw_merchant?: string;
  bank?: string;
  amount: number;
  period: string;
  period_days: number | null;
  confidence: number;
  confidence_label?: string;
  charge_count: number;
  renewal_day?: number;
  last_charge: string;
  reason?: string;
  needs_review?: boolean;
  missed_cycles?: number;
  source?: "subscription-sense" | "manual";
};

type RenewalPrediction = {
  subscription: string;
  next_charge_date: string;
  days_until_charge: number;
  period: string;
  period_days: number;
  confidence_label: "high" | "medium" | "low";
  data_points: number;
};

type TrialAlert = {
  merchant: string;
  trial_score: number;
  type: "trial_to_paid" | "promotional";
  first_charge: number;
  current_charge: number;
  charge_count: number;
  description: string;
};

type PriceChange = {
  subscription: string;
  type: "price_increase" | "price_decrease";
  date: string;
  description: string;
  old_amount: number;
  new_amount: number;
  change_amount: number;
  change_percent: number;
};

type SubscriptionAnalysis = {
  bank_detected: string;
  transactions_parsed: number;
  currency: string;
  categories: Record<string, number>;
  summary: {
    total_subscriptions: number;
    total_possible_subscriptions?: number;
    total_sub_cost: number;
    total_trial_alerts: number;
    total_price_changes: number;
  };
  currency_summary?: {
    exchange_rate: number;
    original_currency: string;
    total_debits_local: number;
    total_debits_usd: number;
    total_credits_usd: number;
    subscription_spend_local?: number;
    subscription_spend_usd?: number;
  };
  subscriptions: SubscriptionResult[];
  possible_subscriptions?: SubscriptionResult[];
  renewal_predictions?: RenewalPrediction[];
  trial_alerts?: TrialAlert[];
  price_changes?: PriceChange[];
};

type PossibleSubscriptionDraft = {
  merchant: string;
  amount: string;
  renewalDay: string;
  period: string;
};

export default function SubscriptionSensePage() {
  const [file, setFile] = useState<File | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SubscriptionAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [merchantLabels, setMerchantLabels] = useState<Record<string, string>>({});
  const [possibleSubscriptionEdits, setPossibleSubscriptionEdits] = useState<
    Record<string, PossibleSubscriptionDraft>
  >({});
  const [showManualSubscription, setShowManualSubscription] = useState(false);
  const [manualSubscription, setManualSubscription] = useState({
    merchant: "",
    amount: "",
    renewalDay: "",
    bank: "",
    period: "monthly",
  });
  const [swapped, setSwapped] = useState(false);
  const [swapComplete, setSwapComplete] = useState(false);
  const [preferences, setPreferences] = useState<UserPreferences>(
    () => readUserPreferences() || DEFAULT_USER_PREFERENCES
  );
  const [capInput, setCapInput] = useState(() => {
    const savedPreferences = readUserPreferences();
    return savedPreferences?.monthlySubscriptionCapJmd
      ? String(savedPreferences.monthlySubscriptionCapJmd)
      : "";
  });
  const [preferencesSubmitted, setPreferencesSubmitted] = useState(
    () => Boolean(readUserPreferences())
  );
  const [preferenceGateActive, setPreferenceGateActive] = useState(false);

  const nextChargeDateForDay = (renewalDay: number) => {
    const today = new Date();
    const next = new Date(today.getFullYear(), today.getMonth(), Math.min(renewalDay, 28));
    if (next < today) next.setMonth(next.getMonth() + 1);
    return next.toISOString().slice(0, 10);
  };

  const periodDaysForPeriod = (period: string) => {
    const normalized = period.toLowerCase();
    if (normalized === "weekly") return 7;
    if (normalized === "biweekly") return 14;
    if (normalized === "quarterly") return 90;
    if (normalized === "yearly") return 365;
    return 30;
  };

  const mergeManualSubscriptions = (analysis: SubscriptionAnalysis): SubscriptionAnalysis => {
    const existingNames = new Set(
      analysis.subscriptions.map((sub) => sub.merchant.trim().toLowerCase())
    );
    const manualRows = readSharedSubscriptions()
      .filter((sub) => sub.source === "manual" && !existingNames.has(sub.name.trim().toLowerCase()))
      .map((sub): SubscriptionResult => {
        const renewalDay = Math.min(Math.max(Math.round(sub.renewalDay || 1), 1), 31);
        return {
          merchant: sub.name,
          raw_merchant: sub.bank,
          bank: sub.bank,
          amount: sub.cost,
          period: sub.period || "monthly",
          period_days: 30,
          confidence: 1,
          confidence_label: "manual",
          charge_count: 1,
          renewal_day: renewalDay,
          last_charge: nextChargeDateForDay(renewalDay),
          reason: "Added manually by the user.",
          needs_review: false,
          missed_cycles: 0,
          source: "manual",
        };
      });

    if (manualRows.length === 0) return analysis;
    const manualTotal = manualRows.reduce((sum, sub) => sum + sub.amount, 0);
    const nextLocalSpend =
      (analysis.currency_summary?.subscription_spend_local ?? analysis.summary.total_sub_cost) +
      manualTotal;

    return {
      ...analysis,
      subscriptions: [...analysis.subscriptions, ...manualRows],
      summary: {
        ...analysis.summary,
        total_subscriptions: analysis.summary.total_subscriptions + manualRows.length,
        total_sub_cost: Number((analysis.summary.total_sub_cost + manualTotal).toFixed(2)),
      },
      currency_summary: analysis.currency_summary
        ? {
            ...analysis.currency_summary,
            subscription_spend_local: Number(nextLocalSpend.toFixed(2)),
            subscription_spend_usd: analysis.currency_summary.exchange_rate
              ? Number((nextLocalSpend / analysis.currency_summary.exchange_rate).toFixed(2))
              : analysis.currency_summary.subscription_spend_usd,
          }
        : analysis.currency_summary,
    };
  };

  useEffect(() => {
    const savedAnalysis = readSubscriptionAnalysis<SubscriptionAnalysis>();
    if (savedAnalysis) {
      // Restore the last completed analysis when the user returns to the page.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setResults(mergeManualSubscriptions(savedAnalysis));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!results) return;

    const subscriptionsWithLabels = (results.subscriptions || []).map((sub, idx) => {
      const labelKey = `${sub.merchant}-${sub.last_charge}-${idx}`;
      return {
        ...sub,
        merchant: (merchantLabels[labelKey] || sub.merchant).trim(),
      };
    });

    saveSharedSubscriptions(
      subscriptionsWithLabels.map((sub, idx) => {
        return {
          id: idx + 1,
          name: sub.merchant,
          cost: sub.amount,
          renewalDay: sub.renewal_day,
          period: sub.period,
          bank: sub.bank,
          source: sub.source ?? "subscription-sense",
        };
      })
    );
    saveSubscriptionAnalysis({ ...results, subscriptions: subscriptionsWithLabels });
  }, [results, merchantLabels]);

  const addManualSubscription = (event: React.FormEvent) => {
    event.preventDefault();
    if (!results) return;

    const merchant = manualSubscription.merchant.trim();
    const amount = Number(manualSubscription.amount);
    const renewalDay = Number(manualSubscription.renewalDay);
    if (
      !merchant ||
      !Number.isFinite(amount) ||
      amount <= 0 ||
      !Number.isFinite(renewalDay) ||
      renewalDay < 1 ||
      renewalDay > 31
    ) {
      setError("Add a name, amount, and renewal day for the manual subscription.");
      return;
    }

    const safeRenewalDay = Math.min(Math.max(Math.round(renewalDay), 1), 31);
    const nextChargeDate = nextChargeDateForDay(safeRenewalDay);
    const manualRow: SubscriptionResult = {
      merchant,
      raw_merchant: manualSubscription.bank.trim() || undefined,
      bank: manualSubscription.bank.trim() || undefined,
      amount: Number(amount.toFixed(2)),
      period: manualSubscription.period || "monthly",
      period_days: 30,
      confidence: 1,
      confidence_label: "manual",
      charge_count: 1,
      renewal_day: safeRenewalDay,
      last_charge: nextChargeDate,
      reason: "Added manually by the user.",
      needs_review: false,
      missed_cycles: 0,
      source: "manual",
    };

    setResults((current) => {
      if (!current) return current;
      const baseLocalSpend =
        current.currency_summary?.subscription_spend_local ?? current.summary.total_sub_cost;
      const nextLocalSpend = Number((baseLocalSpend + manualRow.amount).toFixed(2));

      return {
        ...current,
        subscriptions: [...current.subscriptions, manualRow],
        renewal_predictions: [
          ...(current.renewal_predictions || []),
          {
            subscription: merchant,
            next_charge_date: nextChargeDate,
            days_until_charge: Math.max(
              0,
              Math.ceil((new Date(nextChargeDate).getTime() - new Date().getTime()) / 86_400_000)
            ),
            period: manualRow.period,
            period_days: manualRow.period_days || 30,
            confidence_label: "medium",
            data_points: 1,
          },
        ],
        summary: {
          ...current.summary,
          total_subscriptions: current.summary.total_subscriptions + 1,
          total_sub_cost: Number((current.summary.total_sub_cost + manualRow.amount).toFixed(2)),
        },
        currency_summary: current.currency_summary
          ? {
              ...current.currency_summary,
              subscription_spend_local: nextLocalSpend,
              subscription_spend_usd: current.currency_summary.exchange_rate
                ? Number((nextLocalSpend / current.currency_summary.exchange_rate).toFixed(2))
                : current.currency_summary.subscription_spend_usd,
            }
          : current.currency_summary,
      };
    });
    setManualSubscription({
      merchant: "",
      amount: "",
      renewalDay: "",
      bank: "",
      period: "monthly",
    });
    setShowManualSubscription(false);
    setError(null);
  };

  const removeManualSubscription = (index: number) => {
    setResults((current) => {
      if (!current) return current;
      const removed = current.subscriptions[index];
      if (!removed || removed.source !== "manual") return current;

      const baseLocalSpend =
        current.currency_summary?.subscription_spend_local ?? current.summary.total_sub_cost;
      const nextLocalSpend = Number(Math.max(baseLocalSpend - removed.amount, 0).toFixed(2));

      return {
        ...current,
        subscriptions: current.subscriptions.filter((_, idx) => idx !== index),
        renewal_predictions: (current.renewal_predictions || []).filter(
          (prediction) => prediction.subscription !== removed.merchant
        ),
        summary: {
          ...current.summary,
          total_subscriptions: Math.max(current.summary.total_subscriptions - 1, 0),
          total_sub_cost: Number(Math.max(current.summary.total_sub_cost - removed.amount, 0).toFixed(2)),
        },
        currency_summary: current.currency_summary
          ? {
              ...current.currency_summary,
              subscription_spend_local: nextLocalSpend,
              subscription_spend_usd: current.currency_summary.exchange_rate
                ? Number((nextLocalSpend / current.currency_summary.exchange_rate).toFixed(2))
                : current.currency_summary.subscription_spend_usd,
            }
          : current.currency_summary,
      };
    });
  };

  const possibleSubscriptionKey = (sub: SubscriptionResult, index: number) =>
    `${sub.merchant}-${sub.last_charge}-${index}`;

  const getPossibleSubscriptionDraft = (
    sub: SubscriptionResult,
    index: number
  ): PossibleSubscriptionDraft => {
    const key = possibleSubscriptionKey(sub, index);
    const fallbackRenewalDay =
      sub.renewal_day ||
      (sub.last_charge ? Math.min(Math.max(new Date(sub.last_charge).getDate(), 1), 31) : 1);

    return (
      possibleSubscriptionEdits[key] || {
        merchant: sub.merchant,
        amount: String(sub.amount),
        renewalDay: String(fallbackRenewalDay || 1),
        period: sub.period && sub.period !== "unknown" ? sub.period : "monthly",
      }
    );
  };

  const updatePossibleSubscriptionDraft = (
    sub: SubscriptionResult,
    index: number,
    updates: Partial<PossibleSubscriptionDraft>
  ) => {
    const key = possibleSubscriptionKey(sub, index);
    setPossibleSubscriptionEdits((current) => ({
      ...current,
      [key]: {
        ...getPossibleSubscriptionDraft(sub, index),
        ...updates,
      },
    }));
  };

  const dismissPossibleSubscription = (index: number) => {
    setResults((current) => {
      if (!current) return current;
      return {
        ...current,
        possible_subscriptions: (current.possible_subscriptions || []).filter(
          (_, itemIndex) => itemIndex !== index
        ),
        summary: {
          ...current.summary,
          total_possible_subscriptions: Math.max(
            (current.summary.total_possible_subscriptions || 0) - 1,
            0
          ),
        },
      };
    });
  };

  const confirmPossibleSubscription = (sub: SubscriptionResult, index: number) => {
    const draft = getPossibleSubscriptionDraft(sub, index);
    const merchant = draft.merchant.trim();
    const amount = Number(draft.amount);
    const renewalDay = Number(draft.renewalDay);

    if (
      !merchant ||
      !Number.isFinite(amount) ||
      amount <= 0 ||
      !Number.isFinite(renewalDay) ||
      renewalDay < 1 ||
      renewalDay > 31
    ) {
      setError("Add a name, amount, and renewal day before confirming.");
      return;
    }

    const safeRenewalDay = Math.min(Math.max(Math.round(renewalDay), 1), 31);
    const period = draft.period || "monthly";
    const periodDays = periodDaysForPeriod(period);
    const nextChargeDate = nextChargeDateForDay(safeRenewalDay);
    const confirmed: SubscriptionResult = {
      ...sub,
      merchant,
      amount: Number(amount.toFixed(2)),
      period,
      period_days: sub.period_days || periodDays,
      confidence: Math.max(sub.confidence || 0.6, 0.8),
      confidence_label: "manual",
      renewal_day: safeRenewalDay,
      last_charge: sub.last_charge || nextChargeDate,
      reason: "Confirmed from possible subscriptions by the user.",
      needs_review: false,
      source: "manual",
    };

    setResults((current) => {
      if (!current) return current;
      const baseLocalSpend =
        current.currency_summary?.subscription_spend_local ?? current.summary.total_sub_cost;
      const nextLocalSpend = Number((baseLocalSpend + confirmed.amount).toFixed(2));

      return {
        ...current,
        subscriptions: [...current.subscriptions, confirmed],
        possible_subscriptions: (current.possible_subscriptions || []).filter(
          (_, itemIndex) => itemIndex !== index
        ),
        renewal_predictions: [
          ...(current.renewal_predictions || []),
          {
            subscription: merchant,
            next_charge_date: nextChargeDate,
            days_until_charge: Math.max(
              0,
              Math.ceil((new Date(nextChargeDate).getTime() - new Date().getTime()) / 86_400_000)
            ),
            period,
            period_days: periodDays,
            confidence_label: "medium",
            data_points: confirmed.charge_count || 1,
          },
        ],
        summary: {
          ...current.summary,
          total_subscriptions: current.summary.total_subscriptions + 1,
          total_possible_subscriptions: Math.max(
            (current.summary.total_possible_subscriptions || 0) - 1,
            0
          ),
          total_sub_cost: Number((current.summary.total_sub_cost + confirmed.amount).toFixed(2)),
        },
        currency_summary: current.currency_summary
          ? {
              ...current.currency_summary,
              subscription_spend_local: nextLocalSpend,
              subscription_spend_usd: current.currency_summary.exchange_rate
                ? Number((nextLocalSpend / current.currency_summary.exchange_rate).toFixed(2))
                : current.currency_summary.subscription_spend_usd,
            }
          : current.currency_summary,
      };
    });
    setError(null);
  };

  const updateBudgetingStyle = (budgetingStyle: BudgetingStyle) => {
    setPreferences((current) => ({
      ...current,
      budgetingStyle,
      styleMultiplier: BUDGETING_STYLES[budgetingStyle].styleMultiplier,
    }));
  };

  const handlePreferencesSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const cap = Number(capInput.replace(/[^0-9.]/g, ""));
    const nextPreferences = {
      ...preferences,
      monthlySubscriptionCapJmd: Number.isFinite(cap) && cap > 0 ? cap : null,
    };
    saveUserPreferences(nextPreferences);
    setPreferences(nextPreferences);
    setPreferencesSubmitted(true);
    setPreferenceGateActive(false);
  };

  const handleFileSelect = (selected: File) => {
    if (
      selected.type === "application/pdf" ||
      selected.name.endsWith(".csv")
    ) {
      setFile(selected);
      setFiles([selected]);
      setError(null);
    } else {
      setFile(null);
      setFiles([]);
      setError("Please select a valid PDF or CSV bank statement.");
    }
  };

  const handleFilesSelect = (selectedFiles: File[]) => {
    const validFiles = selectedFiles.filter(
      (selected) =>
        selected.type === "application/pdf" ||
        selected.name.toLowerCase().endsWith(".pdf") ||
        selected.name.toLowerCase().endsWith(".csv")
    );

    if (validFiles.length !== selectedFiles.length) {
      setError("Please select only PDF or CSV bank statements.");
      setFile(null);
      setFiles([]);
      return;
    }

    if (validFiles.length > 3) {
      setError("Please select a maximum of 3 statements.");
      setFile(null);
      setFiles([]);
      return;
    }

    setFiles(validFiles);
    setFile(validFiles[0] || null);
    setError(null);
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    setLoading(true);
    setError(null);
    setResults(null);
    setPreferenceGateActive(!preferencesSubmitted);

    const formData = new FormData();
    files.forEach((selectedFile) => {
      formData.append(files.length > 1 ? "files" : "file", selectedFile);
    });

    let timeoutId: number | null = null;

    try {
      const apiBase =
        process.env.NODE_ENV === "production"
          ? (process.env.NEXT_PUBLIC_BACKEND_URL || FALLBACK_BACKEND_URL).replace(
              /\/$/,
              ""
            )
          : "";
      const uploadUrl =
        files.length > 1
          ? `${apiBase}/api/subscription/upload-multiple`
          : `${apiBase}/api/subscription/upload`;
      const controller = new AbortController();
      timeoutId = window.setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);
      const response = await fetch(uploadUrl, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      const raw = await response.text();
      let data: { detail?: string; error?: string; [key: string]: unknown } = {};
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch {
        if (!response.ok) {
          throw new Error(raw || `Request failed with status ${response.status}`);
        }
        throw new Error("The server returned an invalid response.");
      }
      if (!response.ok)
        throw new Error(
          data.detail || data.error || "Failed to process statement"
        );
      const analysis = mergeManualSubscriptions(data as SubscriptionAnalysis);
      saveSubscriptionAnalysis(analysis);
      setResults(analysis);
      setMerchantLabels({});
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setError(
          "This analysis is taking longer than expected. Try again with fewer statements, or try one statement first to confirm the backend is responding."
        );
      } else if (err instanceof TypeError && err.message === "Failed to fetch") {
        setError(
          "Could not reach the backend. Check that the backend Cloud Run service is deployed and allows this Firebase domain."
        );
      } else {
        setError(err instanceof Error ? err.message : "An error occurred");
      }
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId);
      setLoading(false);
    }
  };

  const shouldAskPreferences = preferenceGateActive && !preferencesSubmitted;
  const canShowResults = results && !shouldAskPreferences;

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
          <h1 className="font-light text-4xl md:text-5xl tracking-tighter leading-tight mb-2">
            SubscriptionSense
          </h1>
          <p className="text-muted-foreground">
            Detect, track, and predict all your recurring subscriptions.
          </p>
        </motion.div>

        <AnimatePresence mode="wait">
          {!canShowResults ? (
            /* ── Upload Form ── */
            <motion.div
              key="upload"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.4 }}
              onAnimationComplete={() => setSwapped(true)}
              className="flex flex-col md:flex-row gap-10 items-center max-w-4xl mx-auto"
            >
              <motion.div
                layout
                className={`flex-1 flex items-center justify-center z-10 ${swapped ? "md:order-2" : "md:order-1"}`}
                transition={{
                  layout: {
                    type: "tween",
                    duration: swapComplete ? 0.3 : 2.5,
                    ease: [0.45, 0, 0.15, 1],
                  },
                }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src="/bankcard.png"
                  alt="Bank card"
                  className="w-full max-w-[456px] rounded-2xl drop-shadow-[0_20px_40px_rgba(0,0,0,0.4)]"
                />
              </motion.div>

              <motion.div
                layout
                className={`flex-1 z-20 ${swapped ? "md:order-1" : "md:order-2"}`}
                transition={{
                  layout: {
                    type: "tween",
                    duration: swapComplete ? 0.3 : 2.5,
                    ease: [0.45, 0, 0.15, 1],
                  },
                }}
                onLayoutAnimationComplete={() => {
                  if (swapped) setSwapComplete(true);
                }}
              >
                <MotionCard className="w-full" hover={false}>
                  <div className="mb-6">
                    <h2 className="text-xl font-medium mb-1">
                      Upload Bank Statement
                    </h2>
                    <p className="text-sm text-muted-foreground">
                      Upload any bank statement PDF. We support multiple banks and
                      currencies.
                    </p>
                  </div>

                  <div className="mb-5">
                    <FileUpload
                      file={file}
                      onFileSelect={handleFileSelect}
                      files={files}
                      onFilesSelect={handleFilesSelect}
                      multiple
                      maxFiles={3}
                      onClear={() => {
                        setFile(null);
                        setFiles([]);
                      }}
                      hint="Upload 1-3 successive statements from any supported bank"
                    />
                  </div>

                  {error && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      className="flex gap-2 items-center px-4 py-3 bg-red-500/10 text-red-600 dark:text-red-400 rounded-xl mb-5 text-sm"
                    >
                      <AlertTriangle size={16} />
                      <span>{error}</span>
                    </motion.div>
                  )}

                  <button
                    disabled={files.length === 0 || loading || Boolean(results)}
                    onClick={handleUpload}
                    className="w-full py-3 flex items-center justify-center gap-2 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl font-medium transition-colors shadow-sm"
                  >
                    {loading ? (
                      <>
                        <span className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
                        Analyzing subscriptions...
                      </>
                    ) : results && shouldAskPreferences ? (
                      "Analysis ready"
                    ) : (
                      files.length > 1 ? "Analyze Statements" : "Detect Subscriptions"
                    )}
                  </button>
                </MotionCard>

                {shouldAskPreferences && (
                  <MotionCard className="w-full mt-4" hover={false}>
                    <form onSubmit={handlePreferencesSubmit}>
                      <div className="mb-5">
                        <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
                          While you wait
                        </p>
                        <h2 className="text-lg font-medium">
                          Answer a few quick questions
                        </h2>
                      </div>

                      <div className="mb-5">
                        <label className="block text-[0.85rem] font-medium mb-2">
                          Budgeting Style
                        </label>
                        <div className="grid grid-cols-3 gap-2">
                          {(Object.keys(BUDGETING_STYLES) as BudgetingStyle[]).map((style) => (
                            <button
                              key={style}
                              type="button"
                              onClick={() => updateBudgetingStyle(style)}
                              className={`rounded-xl border px-3 py-2 text-xs font-medium transition-colors ${
                                preferences.budgetingStyle === style
                                  ? "border-primary bg-primary text-primary-foreground"
                                  : "border-border bg-secondary text-secondary-foreground hover:bg-secondary/80"
                              }`}
                            >
                              {BUDGETING_STYLES[style].label}
                            </button>
                          ))}
                        </div>
                      </div>

                      <div className="mb-5 flex items-center justify-between gap-4 rounded-xl bg-secondary px-4 py-3">
                        <div>
                          <p className="text-[0.85rem] font-medium">Student</p>
                          <p className="text-xs text-muted-foreground">
                            Used for student-plan and exam-season suggestions.
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            setPreferences((current) => ({
                              ...current,
                              isStudent: !current.isStudent,
                            }))
                          }
                          className={`relative h-7 w-12 rounded-full transition-colors ${
                            preferences.isStudent ? "bg-primary" : "bg-muted"
                          }`}
                          aria-pressed={preferences.isStudent}
                        >
                          <span
                            className={`absolute top-1 h-5 w-5 rounded-full bg-white transition-all ${
                              preferences.isStudent ? "left-6" : "left-1"
                            }`}
                          />
                        </button>
                      </div>

                      <div className="mb-5">
                        <label className="block text-[0.85rem] font-medium mb-1.5">
                          Monthly subscription budget cap
                        </label>
                        <div className="flex items-center gap-2 rounded-xl border border-border bg-background px-3">
                          <span className="text-sm text-muted-foreground">JMD</span>
                          <input
                            type="number"
                            min="1"
                            step="1"
                            required
                            value={capInput}
                            onChange={(event) => setCapInput(event.target.value)}
                            placeholder="12000"
                            className="w-full border-0 bg-transparent px-0 focus:ring-0"
                          />
                        </div>
                      </div>

                      <button
                        type="submit"
                        className="w-full rounded-xl bg-primary py-3 font-medium text-primary-foreground transition-colors hover:bg-primary/90"
                      >
                        Submit
                      </button>
                    </form>
                  </MotionCard>
                )}
              </motion.div>
            </motion.div>
          ) : (
            /* ── Results ── */
            <motion.div
              key="results"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="grid grid-cols-1 md:grid-cols-3 gap-6"
            >
              {/* ── Left Column ── */}
              <div className="flex flex-col gap-6">
                {/* Summary Card */}
                <MotionCard hover={false} delay={0}>
                  <h3 className="font-medium mb-4 text-[0.95rem]">
                    Analysis Summary
                  </h3>
                  {[
                    [
                      "Bank Detected",
                      results.bank_detected,
                    ],
                    [
                      "Transactions",
                      results.transactions_parsed,
                    ],
                    [
                      "Currency",
                      results.currency,
                    ],
                    [
                      "Subscriptions Found",
                      results.summary.total_subscriptions,
                      "text-green-600 dark:text-green-400",
                    ],
                    [
                      "Possible Subs",
                      results.summary.total_possible_subscriptions || 0,
                      "text-yellow-600 dark:text-yellow-500",
                    ],
                    [
                      "Monthly Sub Cost",
                      `$${results.summary.total_sub_cost.toLocaleString(
                        undefined,
                        { minimumFractionDigits: 2 }
                      )}`,
                      "text-yellow-600 dark:text-yellow-500",
                    ],
                    [
                      "Trial Alerts",
                      results.summary.total_trial_alerts,
                      results.summary.total_trial_alerts > 0
                        ? "text-orange-600 dark:text-orange-400"
                        : "",
                    ],
                    [
                      "Price Changes",
                      results.summary.total_price_changes,
                    ],
                  ].map(([label, value, colorClass], i) => (
                    <div
                      key={i}
                      className="flex justify-between items-center py-2.5 border-b border-border text-[0.88rem] last:border-0"
                    >
                      <span className="text-muted-foreground">
                        {label as string}
                      </span>
                      <span
                        className={`font-medium ${
                          (colorClass as string) || "text-foreground"
                        }`}
                      >
                        {value as string}
                      </span>
                    </div>
                  ))}
                </MotionCard>

                {/* Currency Summary */}
                {results.currency_summary && (
                  <MotionCard hover={false} delay={0.1}>
                    <h3 className="font-medium mb-3 text-[0.95rem]">
                      Currency Summary
                    </h3>
                    <div className="text-sm space-y-2">
                      <div className="flex justify-between py-1.5 border-b border-border">
                        <span className="text-muted-foreground">
                          Exchange Rate
                        </span>
                        <span className="font-medium">
                          1 USD ={" "}
                          {results.currency_summary.exchange_rate.toLocaleString()}{" "}
                          {results.currency_summary.original_currency}
                        </span>
                      </div>
                      <div className="flex justify-between py-1.5 border-b border-border">
                        <span className="text-muted-foreground">
                          Subscription Spend ({results.currency_summary.original_currency})
                        </span>
                        <span className="font-medium text-red-600 dark:text-red-400">
                          $
                          {(
                            results.currency_summary.subscription_spend_local ??
                            results.summary.total_sub_cost
                          ).toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                          })}
                        </span>
                      </div>
                      <div className="flex justify-between py-1.5 border-b border-border">
                        <span className="text-muted-foreground">
                          Subscription Spend (USD)
                        </span>
                        <span className="font-medium text-red-600 dark:text-red-400">
                          $
                          {(
                            results.currency_summary.subscription_spend_usd ??
                            results.summary.total_sub_cost /
                              results.currency_summary.exchange_rate
                          ).toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                          })}
                        </span>
                      </div>
                    </div>
                  </MotionCard>
                )}

                {/* Category Breakdown */}
                <MotionCard hover={false} delay={0.15}>
                  <h3 className="font-medium mb-3 text-[0.95rem]">
                    Transaction Categories
                  </h3>
                  <div className="space-y-1.5">
                    {Object.entries(results.categories)
                      .sort(
                        ([, a], [, b]) =>
                          (b as number) - (a as number)
                      )
                      .map(([cat, count]) => {
                        const total = results.transactions_parsed;
                        const pct = Math.round(
                          ((count as number) / total) * 100
                        );
                        return (
                          <div key={cat} className="flex items-center gap-3">
                            <span className="text-xs text-muted-foreground w-24 capitalize">
                              {cat === "subscription"
                                ? "Subscription-like"
                                : cat.replace(/_/g, " ")}
                            </span>
                            <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                              <div
                                className="h-full bg-primary/60 rounded-full transition-all"
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                            <span className="text-xs font-medium w-8 text-right">
                              {count as number}
                            </span>
                          </div>
                        );
                      })}
                  </div>
                </MotionCard>

                <button
                  onClick={() => {
                    clearSubscriptionAnalysis();
                    setResults(null);
                    setFile(null);
                    setFiles([]);
                  }}
                  className="w-full py-2.5 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-xl text-sm font-medium transition-colors border border-border"
                >
                  Process Another Statement
                </button>
              </div>

              {/* ── Right Column (2/3 width) ── */}
              <div className="flex flex-col gap-6 md:col-span-2">
                {/* ── Renewal Predictions ── */}
                {results.renewal_predictions &&
                  results.renewal_predictions.length > 0 && (
                    <MotionCard
                      hover={false}
                      delay={0.1}
                      className="border-border bg-secondary"
                    >
                      <div className="flex items-center justify-between mb-4">
                        <h2 className="text-lg font-medium m-0 flex items-center gap-2">
                          <Calendar size={18} />
                          Upcoming Renewals
                        </h2>
                        <Badge variant="info">PREDICTED</Badge>
                      </div>
                      <div className="flex flex-col gap-3">
                        {results.renewal_predictions.map(
                          (pred: RenewalPrediction, idx: number) => {
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
                              <div
                                key={idx}
                                className="flex items-center gap-4 px-4 py-3.5 rounded-xl bg-background border border-border"
                              >
                                <div className="text-center min-w-[3.5rem]">
                                  <p
                                    className={`text-2xl font-medium leading-none ${urgencyColor}`}
                                  >
                                    {pred.days_until_charge}
                                  </p>
                                  <p className="text-[0.65rem] text-muted-foreground mt-0.5">
                                    days
                                  </p>
                                </div>
                                <div className="flex-1">
                                  <p className="font-medium text-sm">
                                    {pred.subscription}
                                  </p>
                                  <p className="text-xs text-muted-foreground mt-0.5">
                                    Next:{" "}
                                    <span className="font-medium text-foreground">
                                      {pred.next_charge_date}
                                    </span>
                                    <span className="mx-1.5 opacity-30">|</span>
                                    {pred.period} (~{pred.period_days} days)
                                  </p>
                                </div>
                                <div className="text-right">
                                  <Badge
                                    variant={
                                      confVariant as
                                        | "safe"
                                        | "warn"
                                        | "danger"
                                    }
                                    className="capitalize"
                                  >
                                    {pred.confidence_label}
                                  </Badge>
                                  <p className="text-[0.7rem] text-muted-foreground mt-1">
                                    {pred.data_points} data pt
                                    {pred.data_points !== 1 ? "s" : ""}
                                  </p>
                                </div>
                              </div>
                            );
                          }
                        )}
                      </div>
                    </MotionCard>
                  )}

                {/* ── Subscriptions Detected ── */}
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2 }}
                >
                  <div className="flex flex-col gap-3 border-b border-border pb-3 mb-4 sm:flex-row sm:items-center sm:justify-between">
                    <h2 className="text-xl font-medium flex items-center gap-2">
                      <RefreshCw size={18} />
                      Detected Subscriptions
                    </h2>
                    <button
                      type="button"
                      onClick={() => setShowManualSubscription((current) => !current)}
                      className="inline-flex items-center justify-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-secondary"
                    >
                      <Plus size={15} />
                      Add manually
                    </button>
                  </div>
                </motion.div>

                {showManualSubscription && (
                  <MotionCard hover={false} className="border-dashed">
                    <form onSubmit={addManualSubscription} className="space-y-4">
                      <div>
                        <h3 className="text-base font-medium">Manual Subscription</h3>
                        <p className="text-sm text-muted-foreground">
                          Add a subscription from another bank or one that was not detected.
                        </p>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <label className="text-sm font-medium">
                          Name
                          <input
                            value={manualSubscription.merchant}
                            onChange={(event) =>
                              setManualSubscription((current) => ({
                                ...current,
                                merchant: event.target.value,
                              }))
                            }
                            placeholder="Netflix"
                            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                          />
                        </label>
                        <label className="text-sm font-medium">
                          Bank or source
                          <input
                            value={manualSubscription.bank}
                            onChange={(event) =>
                              setManualSubscription((current) => ({
                                ...current,
                                bank: event.target.value,
                              }))
                            }
                            placeholder="Other bank"
                            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                          />
                        </label>
                        <label className="text-sm font-medium">
                          Amount
                          <input
                            type="number"
                            min="0.01"
                            step="0.01"
                            value={manualSubscription.amount}
                            onChange={(event) =>
                              setManualSubscription((current) => ({
                                ...current,
                                amount: event.target.value,
                              }))
                            }
                            placeholder="1200"
                            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                          />
                        </label>
                        <label className="text-sm font-medium">
                          Renewal day
                          <input
                            type="number"
                            min="1"
                            max="31"
                            step="1"
                            value={manualSubscription.renewalDay}
                            onChange={(event) =>
                              setManualSubscription((current) => ({
                                ...current,
                                renewalDay: event.target.value,
                              }))
                            }
                            placeholder="15"
                            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                          />
                        </label>
                      </div>
                      {error && (
                        <p className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-400">
                          {error}
                        </p>
                      )}
                      <div className="flex flex-col sm:flex-row gap-2">
                        <button
                          type="submit"
                          className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                        >
                          <Plus size={15} />
                          Add Subscription
                        </button>
                        <button
                          type="button"
                          onClick={() => setShowManualSubscription(false)}
                          className="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-secondary"
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  </MotionCard>
                )}

                {results.subscriptions.map((sub: SubscriptionResult, idx: number) => {
                  const labelKey = `${sub.merchant}-${sub.last_charge}-${idx}`;
                  const displayMerchant = merchantLabels[labelKey] || sub.merchant;
                  const confColor =
                    sub.confidence >= 0.8
                      ? "border-l-green-500"
                      : sub.confidence >= 0.5
                      ? "border-l-yellow-500"
                      : "border-l-orange-500";
                  const confVariant =
                    sub.confidence >= 0.8
                      ? "safe"
                      : sub.confidence >= 0.5
                      ? "warn"
                      : "danger";
                  return (
                    <MotionCard
                      key={idx}
                      delay={0.1 * idx + 0.25}
                      hover={false}
                      className={`border-l-[3px] ${confColor}`}
                    >
                      <div className="flex justify-between items-start mb-3">
                        <div>
                          <h3 className="text-base font-medium flex items-center gap-2 mb-1">
                            {displayMerchant}
                            <Badge
                              variant={
                                confVariant as "safe" | "warn" | "danger"
                              }
                            >
                              {Math.round(sub.confidence * 100)}% confidence
                            </Badge>
                            {sub.needs_review && (
                              <Badge variant="warn">REVIEW NAME</Badge>
                            )}
                            {sub.source === "manual" && (
                              <Badge variant="info">MANUAL</Badge>
                            )}
                          </h3>
                          <p className="text-sm text-muted-foreground">
                            Billing: {sub.period} (~{sub.period_days} days) •
                            Day {sub.renewal_day}
                          </p>
                          {sub.bank && (
                            <p className="text-xs text-muted-foreground mt-1">
                              Source: {sub.bank}
                            </p>
                          )}
                        </div>
                        <div className="text-right flex flex-col items-end gap-2">
                          <p className="text-xl font-medium text-yellow-600 dark:text-yellow-500">
                            $
                            {sub.amount.toLocaleString(undefined, {
                              minimumFractionDigits: 2,
                            })}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            per {sub.period}
                          </p>
                          {sub.source === "manual" && (
                            <button
                              type="button"
                              onClick={() => removeManualSubscription(idx)}
                              className="inline-flex items-center gap-1 rounded-lg border border-red-500/25 px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-500/10 dark:text-red-400"
                            >
                              <Trash2 size={13} />
                              Remove
                            </button>
                          )}
                        </div>
                      </div>

                      {sub.needs_review && (
                        <div className="mb-3 rounded-lg border border-border bg-secondary/60 p-3">
                          <p className="text-xs text-muted-foreground mb-2">
                            Confirm or rename this subscription for your own records.
                          </p>
                          <div className="flex flex-col sm:flex-row gap-2">
                            <input
                              value={merchantLabels[labelKey] ?? sub.merchant}
                              onChange={(event) =>
                                setMerchantLabels((current) => ({
                                  ...current,
                                  [labelKey]: event.target.value,
                                }))
                              }
                              className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                            />
                            <button
                              type="button"
                              onClick={() =>
                                setMerchantLabels((current) => ({
                                  ...current,
                                  [labelKey]: current[labelKey] || sub.merchant,
                                }))
                              }
                              className="rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-background"
                            >
                              Confirm
                            </button>
                          </div>
                          {sub.raw_merchant && (
                            <p className="text-[0.7rem] text-muted-foreground mt-2">
                              Raw: {sub.raw_merchant}
                            </p>
                          )}
                        </div>
                      )}

                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-2 text-[0.82rem]">
                        {[
                          ["Charges Found", `${sub.charge_count} transactions`],
                          ["Last Charge", sub.last_charge],
                          ["Renewal Day", `Day ${sub.renewal_day}`],
                        ].map(([label, val], i) => (
                          <div
                            key={i}
                            className="flex justify-between pb-1.5 border-b border-border"
                          >
                            <span className="text-muted-foreground">
                              {label}
                            </span>
                            <span className="font-medium">{val}</span>
                          </div>
                        ))}
                      </div>
                    </MotionCard>
                  );
                })}

                {results.subscriptions.length === 0 && (
                  <MotionCard hover={false} className="text-center py-12 px-8">
                    <Info
                      size={40}
                      className="text-muted-foreground mx-auto mb-4"
                    />
                    <h3 className="text-base font-medium mb-1.5">
                      No Subscriptions Detected
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      We couldn&apos;t identify any recurring subscription
                      payments. Try uploading a statement with more months of
                      data.
                    </p>
                  </MotionCard>
                )}

                {results.possible_subscriptions &&
                  results.possible_subscriptions.length > 0 && (
                    <MotionCard hover={false} delay={0.3}>
                      <div className="flex items-center justify-between mb-4">
                        <h2 className="text-lg font-medium flex items-center gap-2 m-0">
                          <Info size={18} />
                          Possible Subscriptions
                        </h2>
                        <Badge variant="warn">NEEDS HISTORY</Badge>
                      </div>
                      <div className="flex flex-col gap-3">
                        {results.possible_subscriptions.map((sub: SubscriptionResult, idx: number) => {
                          const draft = getPossibleSubscriptionDraft(sub, idx);
                          return (
                            <div
                              key={possibleSubscriptionKey(sub, idx)}
                              className="p-3.5 rounded-xl bg-background border border-border"
                            >
                              <div className="flex flex-col gap-3">
                                <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                                  <div>
                                    <p className="font-medium text-sm">{sub.merchant}</p>
                                    <p className="text-xs text-muted-foreground">
                                      {sub.charge_count > 1
                                        ? `${sub.charge_count} recurring charges found`
                                        : `One eligible charge on ${sub.last_charge}`}
                                      {sub.period && sub.period !== "unknown"
                                        ? ` • ${sub.period}`
                                        : ""}
                                    </p>
                                  </div>
                                  <span className="font-medium text-yellow-600 dark:text-yellow-500">
                                    $
                                    {sub.amount.toLocaleString(undefined, {
                                      minimumFractionDigits: 2,
                                    })}
                                  </span>
                                </div>

                                <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
                                  <label className="text-sm font-medium sm:col-span-2">
                                    Name
                                    <input
                                      value={draft.merchant}
                                      onChange={(event) =>
                                        updatePossibleSubscriptionDraft(sub, idx, {
                                          merchant: event.target.value,
                                        })
                                      }
                                      className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                                    />
                                  </label>
                                  <label className="text-sm font-medium">
                                    Amount
                                    <input
                                      type="number"
                                      min="0.01"
                                      step="0.01"
                                      value={draft.amount}
                                      onChange={(event) =>
                                        updatePossibleSubscriptionDraft(sub, idx, {
                                          amount: event.target.value,
                                        })
                                      }
                                      className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                                    />
                                  </label>
                                  <label className="text-sm font-medium">
                                    Renewal day
                                    <input
                                      type="number"
                                      min="1"
                                      max="31"
                                      step="1"
                                      value={draft.renewalDay}
                                      onChange={(event) =>
                                        updatePossibleSubscriptionDraft(sub, idx, {
                                          renewalDay: event.target.value,
                                        })
                                      }
                                      className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                                    />
                                  </label>
                                </div>

                                <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                                  <label className="text-sm font-medium sm:w-44">
                                    Period
                                    <select
                                      value={draft.period}
                                      onChange={(event) =>
                                        updatePossibleSubscriptionDraft(sub, idx, {
                                          period: event.target.value,
                                        })
                                      }
                                      className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                                    >
                                      <option value="weekly">Weekly</option>
                                      <option value="biweekly">Biweekly</option>
                                      <option value="monthly">Monthly</option>
                                      <option value="quarterly">Quarterly</option>
                                      <option value="yearly">Yearly</option>
                                    </select>
                                  </label>
                                  <div className="flex flex-col gap-2 sm:flex-row">
                                    <button
                                      type="button"
                                      onClick={() => confirmPossibleSubscription(sub, idx)}
                                      className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                                    >
                                      <Check size={15} />
                                      Confirm
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => dismissPossibleSubscription(idx)}
                                      className="inline-flex items-center justify-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-secondary"
                                    >
                                      <X size={15} />
                                      Dismiss
                                    </button>
                                  </div>
                                </div>

                                {sub.raw_merchant && (
                                  <p className="text-[0.7rem] text-muted-foreground">
                                    Raw: {sub.raw_merchant}
                                  </p>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </MotionCard>
                  )}

                {/* ── Trial Alerts ── */}
                {results.trial_alerts && results.trial_alerts.length > 0 && (
                  <MotionCard
                    hover={false}
                    delay={0.35}
                    className="border-orange-500/30 bg-orange-500/5"
                  >
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="text-lg font-medium m-0">Free Trial Alerts</h2>
                      <Badge variant="warn">ML DETECTED</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mb-4">
                      Merchants whose charge patterns suggest a free trial
                      converting to a paid subscription.
                    </p>
                    <div className="flex flex-col gap-3">
                      {results.trial_alerts.map(
                        (alert: TrialAlert, idx: number) => (
                          <div
                            key={idx}
                            className="p-3.5 rounded-xl bg-background border border-border"
                          >
                            <div className="flex justify-between items-start mb-1.5">
                              <div>
                                <span className="font-medium text-sm">
                                  {alert.merchant}
                                </span>
                                <Badge
                                  variant={
                                    alert.type === "trial_to_paid"
                                      ? "danger"
                                      : "warn"
                                  }
                                  className="ml-2"
                                >
                                  {alert.type === "trial_to_paid"
                                    ? "TRIAL → PAID"
                                    : "PROMO"}
                                </Badge>
                              </div>
                              <span className="text-xs text-muted-foreground font-medium">
                                Score: {Math.round(alert.trial_score * 100)}%
                              </span>
                            </div>
                            <p className="text-sm text-muted-foreground mb-2">
                              {alert.description}
                            </p>
                            <div className="flex gap-4 text-[0.82rem]">
                              <span>
                                <span className="text-muted-foreground">
                                  First:{" "}
                                </span>
                                <span className="font-medium">
                                  $
                                  {alert.first_charge.toLocaleString(
                                    undefined,
                                    { minimumFractionDigits: 2 }
                                  )}
                                </span>
                              </span>
                              <span>
                                <span className="text-muted-foreground">
                                  Now:{" "}
                                </span>
                                <span className="font-medium">
                                  $
                                  {alert.current_charge.toLocaleString(
                                    undefined,
                                    { minimumFractionDigits: 2 }
                                  )}
                                </span>
                              </span>
                              <span className="text-muted-foreground">
                                {alert.charge_count} charges
                              </span>
                            </div>
                          </div>
                        )
                      )}
                    </div>
                  </MotionCard>
                )}

                {/* ── Price Changes ── */}
                {results.price_changes &&
                  results.price_changes.length > 0 && (
                    <MotionCard
                      hover={false}
                      delay={0.4}
                      className="border-yellow-500/30 bg-yellow-500/5"
                    >
                      <div className="flex items-center justify-between mb-4">
                        <h2 className="text-lg font-medium flex items-center gap-2 m-0">
                          {results.price_changes.some(
                            (c: PriceChange) => c.type === "price_increase"
                          ) ? (
                            <TrendingUp
                              size={18}
                              className="text-red-600 dark:text-red-400"
                            />
                          ) : (
                            <TrendingDown
                              size={18}
                              className="text-green-600 dark:text-green-400"
                            />
                          )}
                          Price Changes
                        </h2>
                      </div>
                      <p className="text-sm text-muted-foreground mb-4">
                        We noticed a possible subscription price increase based
                        on your past billing pattern.
                      </p>
                      <div className="flex flex-col gap-3">
                        {results.price_changes.map(
                          (change: PriceChange, idx: number) => (
                            <div
                              key={idx}
                              className="p-3.5 rounded-xl bg-background border border-border"
                            >
                              <div className="flex justify-between items-start mb-1.5">
                                <div>
                                  <span className="font-medium text-sm">
                                    {change.subscription}
                                  </span>
                                  <Badge
                                    variant={
                                      change.type === "price_increase"
                                        ? "danger"
                                        : "safe"
                                    }
                                    className="ml-2"
                                  >
                                    {change.type === "price_increase"
                                      ? "INCREASE"
                                      : "DECREASE"}
                                  </Badge>
                                </div>
                                <span className="text-[0.7rem] text-muted-foreground">
                                  {change.date}
                                </span>
                              </div>
                              <p className="text-sm text-muted-foreground mb-2">
                                {change.description}
                              </p>
                              <div className="flex gap-4 text-[0.82rem]">
                                <span>
                                  <span className="text-muted-foreground">
                                    Before:{" "}
                                  </span>
                                  <span className="font-medium">
                                    $
                                    {change.old_amount.toLocaleString(
                                      undefined,
                                      { minimumFractionDigits: 2 }
                                    )}
                                  </span>
                                </span>
                                <span>
                                  <span className="text-muted-foreground">
                                    After:{" "}
                                  </span>
                                  <span className="font-medium">
                                    $
                                    {change.new_amount.toLocaleString(
                                      undefined,
                                      { minimumFractionDigits: 2 }
                                    )}
                                  </span>
                                </span>
                                <span
                                  className={`font-medium ${
                                    change.change_amount > 0
                                      ? "text-red-600 dark:text-red-400"
                                      : "text-green-600 dark:text-green-400"
                                  }`}
                                >
                                  {change.change_amount > 0 ? "+" : ""}
                                  {change.change_percent}%
                                </span>
                              </div>
                            </div>
                          )
                        )}
                      </div>
                    </MotionCard>
                  )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </>
  );
}
