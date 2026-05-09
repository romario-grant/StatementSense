"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle,
  Info,
  Loader2,
  RefreshCw,
} from "lucide-react";
import Navbar from "@/components/Navbar";
import MotionCard from "@/components/MotionCard";
import Badge from "@/components/Badge";
import { readSubscriptionAnalysis } from "@/lib/subscriptionStore";

const FALLBACK_BACKEND_URL =
  "https://statementsense-backend-430268251728.us-central1.run.app";

type SavedSubscriptionAnalysis = {
  transactions?: Record<string, unknown>[];
  subscriptions?: Record<string, unknown>[];
  price_changes?: Record<string, unknown>[];
  transactions_parsed?: number;
};

export default function RenewalSensePage() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [results, setResults] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasSourceAnalysis, setHasSourceAnalysis] = useState(false);

  useEffect(() => {
    const source = readSubscriptionAnalysis<SavedSubscriptionAnalysis>();
    if (!source?.transactions?.length) {
      // Load the saved browser handoff once when RenewalSense opens.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setHasSourceAnalysis(false);
      setLoading(false);
      return;
    }

    setHasSourceAnalysis(true);
    const apiBase =
      process.env.NODE_ENV === "production"
        ? (process.env.NEXT_PUBLIC_BACKEND_URL || FALLBACK_BACKEND_URL).replace(
            /\/$/,
            ""
          )
        : "";

    fetch(`${apiBase}/api/renewal/analyze-existing`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transactions: source.transactions || [],
        subscriptions: source.subscriptions || [],
        price_changes: source.price_changes || [],
      }),
    })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || data.error || "Renewal analysis failed.");
        }
        return data;
      })
      .then(setResults)
      .catch((err) => {
        setError(err instanceof Error ? err.message : "An error occurred");
      })
      .finally(() => setLoading(false));
  }, []);

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
                <h2 className="text-lg font-medium mb-2">Could Not Build Renewal Insights</h2>
                <p className="text-sm text-muted-foreground mb-6">{error}</p>
                <a
                  href="/subscription"
                  className="inline-flex items-center justify-center rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                >
                  Refresh in SubscriptionSense
                </a>
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

                <MotionCard hover={false} delay={0.1}>
                  <h3 className="font-medium mb-1 text-[0.95rem]">30-Day Paycycle Map</h3>
                  <p className="text-xs text-muted-foreground mb-4">
                    Payday on Day {results.salary.pay_day}.
                  </p>
                  <div className="flex flex-wrap gap-[3px]">
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    {results.paycycle_map.map((day: any) => {
                      let bg = "bg-secondary";
                      if (day.zone === "safe") bg = "bg-green-500 text-white";
                      if (day.zone === "moderate") bg = "bg-yellow-500 text-white";
                      if (day.zone === "high") bg = "bg-orange-500 text-white";
                      if (day.zone === "critical") bg = "bg-red-500 text-white";
                      return (
                        <div
                          key={day.day}
                          title={`Day ${day.day}: ${day.zone.toUpperCase()} ZONE`}
                          className={`w-[calc(10%-3px)] h-7 rounded flex items-center justify-center relative cursor-pointer ${bg} ${day.is_payday ? "border-2 border-border" : ""}`}
                        >
                          {day.is_payday && (
                            <span className="absolute -top-4 text-[0.5rem] font-medium bg-primary text-white px-1 py-px rounded-[3px] whitespace-nowrap">
                              PAY
                            </span>
                          )}
                          {day.subscription && (
                            <span className="text-[0.6rem] font-medium text-white">
                              {day.subscription.substring(0, 1)}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <div className="flex gap-3 mt-3 text-[0.7rem] text-muted-foreground">
                    {[
                      ["Safe", "bg-green-500"],
                      ["Mid", "bg-yellow-500"],
                      ["Caution", "bg-orange-500"],
                      ["Danger", "bg-red-500"],
                    ].map(([label, colorClass]) => (
                      <div key={label} className="flex items-center gap-1">
                        <span className={`w-2.5 h-2.5 rounded-sm ${colorClass}`} />
                        {label}
                      </div>
                    ))}
                  </div>
                </MotionCard>

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
                          ["Financial Load", `${Math.round(sub.breakdown.load_factor * 100)}% of salary consumed`],
                          ["Failure History", `${sub.fail_history} failed attempts`],
                          ["Expense Clustering", `$${sub.breakdown.cluster_amount.toLocaleString()} within +/-3 days`],
                        ].map(([label, val], i) => (
                          <div key={i} className="flex justify-between pb-1.5 border-b border-border">
                            <span className="text-muted-foreground">{label}</span>
                            <span className="font-medium">{val}</span>
                          </div>
                        ))}
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
