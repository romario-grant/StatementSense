"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle,
  Info,
} from "lucide-react";
import Navbar from "@/components/Navbar";
import MotionCard from "@/components/MotionCard";
import Badge from "@/components/Badge";
import FileUpload from "@/components/FileUpload";

export default function RenewalSensePage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [swapped, setSwapped] = useState(false);
  const [swapComplete, setSwapComplete] = useState(false);

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
      const response = await fetch("/api/renewal/upload", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(data.detail || data.error || "Failed to process statement");
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
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
            RenewalSense
          </h1>
          <p className="text-muted-foreground">
            Predict subscription renewal failures before they happen.
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
              onAnimationComplete={() => setSwapped(true)}
              className="flex gap-10 items-center max-w-4xl mx-auto"
            >
              {/* Bankcard Image */}
              <motion.div
                layout
                className={`flex-1 flex items-center justify-center z-10 ${swapped ? 'order-2' : 'order-1'}`}
                transition={{ layout: { type: "tween", duration: swapComplete ? 0.3 : 2.5, ease: [0.45, 0, 0.15, 1] } }}
              >
                <img
                  src="/bankcard.png"
                  alt="Bank Card"
                  className="w-full max-w-[456px] rounded-2xl drop-shadow-[0_20px_40px_rgba(0,0,0,0.4)]"
                />
              </motion.div>

              {/* Upload Form */}
              <motion.div
                layout
                className={`flex-1 z-20 ${swapped ? 'order-1' : 'order-2'}`}
                transition={{ layout: { type: "tween", duration: swapComplete ? 0.3 : 2.5, ease: [0.45, 0, 0.15, 1] } }}
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
                      Select your recent PDF or CSV statement. All processing is done server-side.
                    </p>
                  </div>

                  <div className="mb-5">
                    <FileUpload
                      file={file}
                      onFileSelect={handleFileSelect}
                      onClear={() => setFile(null)}
                      hint="Supports PDF (Scotia Bank Jamaica) and CSV"
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
                        Analyzing Statement...
                      </>
                    ) : (
                      "Process Statement"
                    )}
                  </button>
                </MotionCard>
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
              {/* Left Column */}
              <div className="flex flex-col gap-6">
                {/* Summary */}
                <MotionCard hover={false} delay={0}>
                  <h3 className="font-medium mb-4 text-[0.95rem]">Analysis Summary</h3>
                  {[
                    ["Transactions Found", results.transactions_parsed],
                    ["Monthly Income", `$${results.salary.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, "text-green-600 dark:text-green-400"],
                    ["Payday", `Day ${results.salary.pay_day}`],
                    ["Total Subscriptions", results.summary.total_subscriptions],
                    ["Monthly Subs Cost", `$${results.summary.total_sub_cost.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, "text-yellow-600 dark:text-yellow-500"],
                  ].map(([label, value, colorClass], i) => (
                    <div
                      key={i}
                      className="flex justify-between items-center py-2.5 border-b border-border text-[0.88rem] last:border-0"
                    >
                      <span className="text-muted-foreground">{label}</span>
                      <span className={`font-medium ${colorClass || "text-foreground"}`}>{value}</span>
                    </div>
                  ))}
                </MotionCard>

                {/* Paycycle Map */}
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
                          className={`w-[calc(10%-3px)] h-7 rounded flex items-center justify-center relative cursor-pointer ${bg} ${day.is_payday ? 'border-2 border-border' : ''}`}
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

                <button
                  onClick={() => { setResults(null); setFile(null); }}
                  className="w-full py-2.5 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-xl text-sm font-medium transition-colors border border-border"
                >
                  Process Another Statement
                </button>
              </div>

              {/* Right Column */}
              <div className="flex flex-col gap-6 md:col-span-2">
                {/* Renewal Predictions */}
                {results.renewal_predictions && results.renewal_predictions.length > 0 && (
                  <MotionCard hover={false} delay={0.15} className="border-border bg-secondary">
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="text-lg font-medium m-0">Upcoming Charges</h2>
                      <Badge variant="info">PREDICTED</Badge>
                    </div>
                    <div className="flex flex-col gap-3">
                      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                      {results.renewal_predictions.map((pred: any, idx: number) => {
                        const urgencyColor = pred.days_until_charge <= 3 ? "text-red-600 dark:text-red-400" : pred.days_until_charge <= 7 ? "text-yellow-600 dark:text-yellow-500" : "text-green-600 dark:text-green-400";
                        const confVariant = pred.confidence_label === "high" ? "safe" : pred.confidence_label === "medium" ? "warn" : "danger";
                        return (
                          <div key={idx} className="flex items-center gap-4 px-4 py-3.5 rounded-xl bg-background border border-border">
                            <div className="text-center min-w-[3.5rem]">
                              <p className={`text-2xl font-medium leading-none ${urgencyColor}`}>{pred.days_until_charge}</p>
                              <p className="text-[0.65rem] text-muted-foreground mt-0.5">days</p>
                            </div>
                            <div className="flex-1">
                              <p className="font-medium text-sm">{pred.subscription}</p>
                              <p className="text-xs text-muted-foreground mt-0.5">
                                Next: <span className="font-medium text-foreground">{pred.next_charge_date}</span>
                                <span className="mx-1.5 opacity-30">|</span>
                                Window: {pred.confidence_window.earliest} — {pred.confidence_window.latest}
                              </p>
                            </div>
                            <div className="text-right">
                              <Badge variant={confVariant as "safe"|"warn"|"danger"} className="capitalize">{pred.confidence_label}</Badge>
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

                {/* Subscription Risk Report */}
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
                  const riskColor = sub.risk_level === "low" ? "border-l-green-500" : sub.risk_level === "moderate" ? "border-l-yellow-500" : "border-l-red-500";
                  const riskVariant = sub.risk_level === "low" ? "safe" : sub.risk_level === "moderate" ? "warn" : "danger";
                  return (
                    <MotionCard key={idx} delay={0.1 * idx + 0.25} hover={false} className={`border-l-[3px] ${riskColor}`}>
                      <div className="flex justify-between items-start mb-3">
                        <div>
                          <h3 className="text-base font-medium flex items-center gap-2 mb-1">
                            {sub.subscription}
                            <Badge variant={riskVariant as "safe"|"warn"|"danger"}>
                              {sub.risk_label.toUpperCase()} RISK ({Math.round(sub.risk_score * 100)}%)
                            </Badge>
                          </h3>
                          <p className="text-sm text-muted-foreground">Renews on Day {sub.renewal_day}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-xl font-medium text-yellow-600 dark:text-yellow-500">${sub.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
                          <p className="text-xs text-muted-foreground">per month</p>
                        </div>
                      </div>

                      <div className="p-3 rounded-lg bg-secondary mb-3">
                        <p className="flex items-start gap-2 text-sm font-medium">
                          {sub.risk_level === "low"
                            ? <CheckCircle size={16} className="text-green-600 dark:text-green-400 shrink-0 mt-0.5" />
                            : <AlertTriangle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />}
                          {sub.advice}
                        </p>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-[0.82rem]">
                        {[
                          ["Paycycle Position", `${sub.breakdown.days_since_payday} days after payday`],
                          ["Financial Load", `${Math.round(sub.breakdown.load_factor * 100)}% of salary consumed`],
                          ["Failure History", `${sub.fail_history} failed attempts`],
                          ["Expense Clustering", `$${sub.breakdown.cluster_amount.toLocaleString()} within ±3 days`],
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

                {results.subscriptions.length === 0 && (
                  <MotionCard hover={false} className="text-center py-12 px-8">
                    <Info size={40} className="text-muted-foreground mx-auto mb-4" />
                    <h3 className="text-base font-medium mb-1.5">No Subscriptions Detected</h3>
                    <p className="text-sm text-muted-foreground">
                      We couldn't identify any recurring subscription payments in this statement.
                    </p>
                  </MotionCard>
                )}

                {/* Price Change Detection */}
                {results.price_changes && results.price_changes.length > 0 && (
                  <MotionCard hover={false} delay={0.4} className="border-yellow-500/30 bg-yellow-500/5">
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="text-lg font-medium flex items-center gap-2 m-0">
                        <AlertTriangle size={18} className="text-yellow-600 dark:text-yellow-500" />
                        Price Change Detection
                      </h2>
                      <Badge variant="warn">CUSUM</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mb-4">
                      Structural billing changes detected using Cumulative Sum analysis.
                    </p>
                    <div className="flex flex-col gap-3">
                      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                      {results.price_changes.map((change: any, idx: number) => (
                        <div key={idx} className="p-3.5 rounded-xl bg-background border border-border">
                          <div className="flex justify-between items-start mb-1.5">
                            <div>
                              <span className="font-medium text-sm">{change.subscription}</span>
                              <Badge
                                variant={change.severity === "warning" ? "danger" : "safe"}
                                className="ml-2"
                              >
                                {change.type}
                              </Badge>
                            </div>
                            <span className="text-[0.7rem] text-muted-foreground">{change.date}</span>
                          </div>
                          <p className="text-sm text-muted-foreground mb-2">{change.description}</p>
                          <div className="flex gap-4 text-[0.82rem]">
                            <span><span className="text-muted-foreground">Before: </span><span className="font-medium">${change.old_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span></span>
                            <span><span className="text-muted-foreground">After: </span><span className="font-medium">${change.new_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span></span>
                            <span className={`font-medium ${change.change_amount > 0 ? "text-red-600 dark:text-red-400" : "text-green-600 dark:text-green-400"}`}>
                              {change.change_amount > 0 ? "+" : ""}{change.change_percent}%
                            </span>
                          </div>
                        </div>
                      ))}
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
