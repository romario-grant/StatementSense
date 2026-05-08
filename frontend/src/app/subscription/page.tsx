"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle,
  Info,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Calendar,
  Shield,
  Zap,
  RefreshCw,
} from "lucide-react";
import Navbar from "@/components/Navbar";
import MotionCard from "@/components/MotionCard";
import Badge from "@/components/Badge";
import FileUpload from "@/components/FileUpload";

const FALLBACK_BACKEND_URL =
  "https://statementsense-backend-430268251728.us-central1.run.app";

export default function SubscriptionSensePage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileSelect = (selected: File) => {
    if (
      selected.type === "application/pdf" ||
      selected.name.endsWith(".csv")
    ) {
      setFile(selected);
      setError(null);
    } else {
      setFile(null);
      setError("Please select a valid PDF or CSV bank statement.");
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResults(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const apiBase =
        process.env.NODE_ENV === "production"
          ? (process.env.NEXT_PUBLIC_BACKEND_URL || FALLBACK_BACKEND_URL).replace(
              /\/$/,
              ""
            )
          : "";
      const uploadUrl = `${apiBase}/api/subscription/upload`;
      const response = await fetch(uploadUrl, {
        method: "POST",
        body: formData,
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
      setResults(data);
    } catch (err) {
      if (err instanceof TypeError && err.message === "Failed to fetch") {
        setError(
          "Could not reach the backend. Check that the backend Cloud Run service is deployed and allows this Firebase domain."
        );
      } else {
        setError(err instanceof Error ? err.message : "An error occurred");
      }
    } finally {
      setLoading(false);
    }
  };

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
          {!results ? (
            /* ── Upload Form ── */
            <motion.div
              key="upload"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.4 }}
              className="max-w-lg mx-auto"
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
                    onClear={() => setFile(null)}
                    hint="Supports any bank — Scotiabank, NCB, JMMB, and more"
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
                  disabled={!file || loading}
                  onClick={handleUpload}
                  className="w-full py-3 flex items-center justify-center gap-2 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl font-medium transition-colors shadow-sm"
                >
                  {loading ? (
                    <>
                      <span className="animate-spin inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
                      Analyzing Subscriptions...
                    </>
                  ) : (
                    "Detect Subscriptions"
                  )}
                </button>
              </MotionCard>
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
                    <h3 className="font-medium mb-3 text-[0.95rem] flex items-center gap-2">
                      <DollarSign size={16} />
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
                          Total Spent ({results.currency_summary.original_currency})
                        </span>
                        <span className="font-medium text-red-600 dark:text-red-400">
                          $
                          {results.currency_summary.total_debits_local.toLocaleString(
                            undefined,
                            { minimumFractionDigits: 2 }
                          )}
                        </span>
                      </div>
                      <div className="flex justify-between py-1.5 border-b border-border">
                        <span className="text-muted-foreground">
                          Total Spent (USD)
                        </span>
                        <span className="font-medium text-red-600 dark:text-red-400">
                          $
                          {results.currency_summary.total_debits_usd.toLocaleString(
                            undefined,
                            { minimumFractionDigits: 2 }
                          )}
                        </span>
                      </div>
                      <div className="flex justify-between py-1.5">
                        <span className="text-muted-foreground">
                          Total Received (USD)
                        </span>
                        <span className="font-medium text-green-600 dark:text-green-400">
                          $
                          {results.currency_summary.total_credits_usd.toLocaleString(
                            undefined,
                            { minimumFractionDigits: 2 }
                          )}
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
                              {cat.replace(/_/g, " ")}
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
                    setResults(null);
                    setFile(null);
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
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        {results.renewal_predictions.map(
                          (pred: any, idx: number) => {
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
                  <h2 className="text-xl font-medium pb-3 border-b border-border mb-4 flex items-center gap-2">
                    <RefreshCw size={18} />
                    Detected Subscriptions
                  </h2>
                </motion.div>

                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {results.subscriptions.map((sub: any, idx: number) => {
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
                            {sub.merchant}
                            <Badge
                              variant={
                                confVariant as "safe" | "warn" | "danger"
                              }
                            >
                              {Math.round(sub.confidence * 100)}% confidence
                            </Badge>
                          </h3>
                          <p className="text-sm text-muted-foreground">
                            Billing: {sub.period} (~{sub.period_days} days) •
                            Day {sub.renewal_day}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-xl font-medium text-yellow-600 dark:text-yellow-500">
                            $
                            {sub.amount.toLocaleString(undefined, {
                              minimumFractionDigits: 2,
                            })}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            per {sub.period}
                          </p>
                        </div>
                      </div>

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

                {/* ── Trial Alerts ── */}
                {results.trial_alerts && results.trial_alerts.length > 0 && (
                  <MotionCard
                    hover={false}
                    delay={0.35}
                    className="border-orange-500/30 bg-orange-500/5"
                  >
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="text-lg font-medium flex items-center gap-2 m-0">
                        <Zap
                          size={18}
                          className="text-orange-600 dark:text-orange-400"
                        />
                        Free Trial Alerts
                      </h2>
                      <Badge variant="warn">ML DETECTED</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mb-4">
                      Merchants whose charge patterns suggest a free trial
                      converting to a paid subscription.
                    </p>
                    <div className="flex flex-col gap-3">
                      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                      {results.trial_alerts.map(
                        (alert: any, idx: number) => (
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
                            // eslint-disable-next-line @typescript-eslint/no-explicit-any
                            (c: any) => c.type === "price_increase"
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
                        <Badge variant="warn">CUSUM</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mb-4">
                        Structural billing changes detected using Cumulative Sum
                        analysis.
                      </p>
                      <div className="flex flex-col gap-3">
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        {results.price_changes.map(
                          (change: any, idx: number) => (
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
