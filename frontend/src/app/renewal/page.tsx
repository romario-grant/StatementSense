"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
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
      <main className="container" style={{ paddingTop: "5rem", paddingBottom: "3rem" }}>
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          style={{ marginBottom: "2rem" }}
        >
          <h1 style={{ fontSize: "2rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "0.3rem" }}>
            RenewalSense
          </h1>
          <p style={{ color: "var(--text-secondary)" }}>
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
              style={{
                display: "flex",
                gap: "2.5rem",
                alignItems: "center",
                maxWidth: "56rem",
                margin: "0 auto",
              }}
            >
              {/* Bankcard Image */}
              <motion.div
                layout
                style={{
                  flex: 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  order: swapped ? 2 : 1,
                  zIndex: 1,
                }}
                transition={{ layout: { type: "tween", duration: swapComplete ? 0.3 : 2.5, ease: [0.45, 0, 0.15, 1] } }}
              >
                <img
                  src="/bankcard.png"
                  alt="Bank Card"
                  style={{
                    width: "100%",
                    maxWidth: "456px",
                    borderRadius: "16px",
                    filter: "drop-shadow(0 20px 40px rgba(0,0,0,0.4))",
                  }}
                />
              </motion.div>

              {/* Upload Form */}
              <motion.div
                layout
                style={{
                  flex: 1,
                  order: swapped ? 1 : 2,
                  zIndex: 2,
                }}
                transition={{ layout: { type: "tween", duration: swapComplete ? 0.3 : 2.5, ease: [0.45, 0, 0.15, 1] } }}
                onLayoutAnimationComplete={() => {
                  if (swapped) setSwapComplete(true);
                }}
              >
                <MotionCard style={{ width: "100%" }} hover={false}>
                  <div style={{ marginBottom: "1.5rem" }}>
                    <h2 style={{ fontSize: "1.15rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                      Upload Bank Statement
                    </h2>
                    <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                      Select your recent PDF or CSV statement. All processing is done server-side.
                    </p>
                  </div>

                  <div style={{ marginBottom: "1.25rem" }}>
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
                      style={{
                        display: "flex",
                        gap: "0.5rem",
                        alignItems: "center",
                        padding: "0.75rem 1rem",
                        background: "var(--status-danger-bg)",
                        color: "var(--status-danger)",
                        borderRadius: "10px",
                        marginBottom: "1.25rem",
                        fontSize: "0.85rem",
                      }}
                    >
                      <AlertTriangle size={16} />
                      <span>{error}</span>
                    </motion.div>
                  )}

                  <button
                    className="btn-primary"
                    disabled={!file || loading}
                    onClick={handleUpload}
                    style={{
                      width: "100%",
                      padding: "0.75rem",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "0.5rem",
                    }}
                  >
                    {loading ? (
                      <>
                        <span className="animate-spin" style={{ display: "inline-block", width: 16, height: 16, border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "#fff", borderRadius: "50%" }} />
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
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 2fr",
                gap: "1.5rem",
              }}
            >
              {/* Left Column */}
              <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                {/* Summary */}
                <MotionCard hover={false} delay={0}>
                  <h3 style={{ fontWeight: 700, marginBottom: "1rem", fontSize: "0.95rem" }}>Analysis Summary</h3>
                  {[
                    ["Transactions Found", results.transactions_parsed],
                    ["Monthly Income", `$${results.salary.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, "var(--status-safe)"],
                    ["Payday", `Day ${results.salary.pay_day}`],
                    ["Total Subscriptions", results.summary.total_subscriptions],
                    ["Monthly Subs Cost", `$${results.summary.total_sub_cost.toLocaleString(undefined, { minimumFractionDigits: 2 })}`, "var(--accent-gold)"],
                  ].map(([label, value, color], i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        padding: "0.6rem 0",
                        borderBottom: "1px solid var(--border-subtle)",
                        fontSize: "0.88rem",
                      }}
                    >
                      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
                      <span style={{ fontWeight: 600, color: (color as string) || "var(--text-primary)" }}>{value}</span>
                    </div>
                  ))}
                </MotionCard>

                {/* Paycycle Map */}
                <MotionCard hover={false} delay={0.1}>
                  <h3 style={{ fontWeight: 700, marginBottom: "0.25rem", fontSize: "0.95rem" }}>30-Day Paycycle Map</h3>
                  <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
                    Payday on Day {results.salary.pay_day}.
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "3px" }}>
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    {results.paycycle_map.map((day: any) => {
                      let bg = "var(--bg-tertiary)";
                      if (day.zone === "safe") bg = "var(--status-safe)";
                      if (day.zone === "moderate") bg = "var(--status-warn)";
                      if (day.zone === "high") bg = "var(--accent-gold-hover)";
                      if (day.zone === "critical") bg = "var(--status-danger)";
                      return (
                        <div
                          key={day.day}
                          title={`Day ${day.day}: ${day.zone.toUpperCase()} ZONE`}
                          style={{
                            width: "calc(10% - 3px)",
                            height: "28px",
                            backgroundColor: bg,
                            borderRadius: "4px",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            position: "relative",
                            border: day.is_payday ? "2px solid var(--accent-teal)" : "none",
                            cursor: "pointer",
                          }}
                        >
                          {day.is_payday && (
                            <span style={{ position: "absolute", top: "-18px", fontSize: "0.5rem", fontWeight: 700, background: "var(--accent-teal)", color: "#fff", padding: "1px 4px", borderRadius: "3px", whiteSpace: "nowrap" }}>
                              PAY
                            </span>
                          )}
                          {day.subscription && (
                            <span style={{ fontSize: "0.6rem", fontWeight: 700, color: "#fff" }}>
                              {day.subscription.substring(0, 1)}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.75rem", fontSize: "0.7rem", color: "var(--text-secondary)" }}>
                    {[
                      ["Safe", "var(--status-safe)"],
                      ["Mid", "var(--status-warn)"],
                      ["Caution", "var(--accent-gold-hover)"],
                      ["Danger", "var(--status-danger)"],
                    ].map(([label, color]) => (
                      <div key={label as string} style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <span style={{ width: 10, height: 10, borderRadius: 2, background: color as string, display: "inline-block" }} />
                        {label}
                      </div>
                    ))}
                  </div>
                </MotionCard>

                <button
                  onClick={() => { setResults(null); setFile(null); }}
                  style={{ width: "100%", padding: "0.6rem" }}
                >
                  Process Another Statement
                </button>
              </div>

              {/* Right Column */}
              <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                {/* Renewal Predictions */}
                {results.renewal_predictions && results.renewal_predictions.length > 0 && (
                  <MotionCard hover={false} delay={0.15} style={{ border: "1px solid var(--accent-teal-border)", background: "rgba(97, 205, 255, 0.03)" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
                      <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0 }}>Upcoming Charges</h2>
                      <Badge variant="teal" style={{ fontSize: "0.65rem" }}>PREDICTED</Badge>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                      {results.renewal_predictions.map((pred: any, idx: number) => {
                        const urgencyColor = pred.days_until_charge <= 3 ? "var(--status-danger)" : pred.days_until_charge <= 7 ? "var(--status-warn)" : "var(--status-safe)";
                        const confVariant = pred.confidence_label === "high" ? "safe" : pred.confidence_label === "medium" ? "warn" : "danger";
                        return (
                          <div key={idx} style={{ display: "flex", alignItems: "center", gap: "1rem", padding: "0.85rem 1rem", borderRadius: "10px", background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)" }}>
                            <div style={{ textAlign: "center", minWidth: "3.5rem" }}>
                              <p style={{ fontSize: "1.4rem", fontWeight: 700, color: urgencyColor, lineHeight: 1 }}>{pred.days_until_charge}</p>
                              <p style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginTop: "2px" }}>days</p>
                            </div>
                            <div style={{ flex: 1 }}>
                              <p style={{ fontWeight: 600, fontSize: "0.9rem" }}>{pred.subscription}</p>
                              <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                                Next: <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{pred.next_charge_date}</span>
                                <span style={{ margin: "0 0.4rem", opacity: 0.3 }}>|</span>
                                Window: {pred.confidence_window.earliest} — {pred.confidence_window.latest}
                              </p>
                            </div>
                            <div style={{ textAlign: "right" }}>
                              <Badge variant={confVariant as "safe"|"warn"|"danger"} style={{ textTransform: "capitalize" }}>{pred.confidence_label}</Badge>
                              <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
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
                  <h2 style={{ fontSize: "1.25rem", fontWeight: 700, paddingBottom: "0.75rem", borderBottom: "1px solid var(--border-subtle)", marginBottom: "1rem" }}>
                    Subscription Risk Report
                  </h2>
                </motion.div>

                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {results.subscriptions.map((sub: any, idx: number) => {
                  const riskColor = sub.risk_level === "low" ? "var(--status-safe)" : sub.risk_level === "moderate" ? "var(--status-warn)" : "var(--status-danger)";
                  const riskVariant = sub.risk_level === "low" ? "safe" : sub.risk_level === "moderate" ? "warn" : "danger";
                  return (
                    <MotionCard key={idx} delay={0.1 * idx + 0.25} hover={false} style={{ borderLeft: `3px solid ${riskColor}` }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
                        <div>
                          <h3 style={{ fontSize: "1.05rem", fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.2rem" }}>
                            {sub.subscription}
                            <Badge variant={riskVariant as "safe"|"warn"|"danger"}>
                              {sub.risk_label.toUpperCase()} RISK ({Math.round(sub.risk_score * 100)}%)
                            </Badge>
                          </h3>
                          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>Renews on Day {sub.renewal_day}</p>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <p style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--accent-gold)" }}>${sub.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
                          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>per month</p>
                        </div>
                      </div>

                      <div style={{ padding: "0.75rem", borderRadius: "8px", background: "var(--bg-secondary)", marginBottom: "0.75rem" }}>
                        <p style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", fontSize: "0.85rem", fontWeight: 500 }}>
                          {sub.risk_level === "low"
                            ? <CheckCircle size={16} style={{ color: "var(--status-safe)", flexShrink: 0, marginTop: 2 }} />
                            : <AlertTriangle size={16} style={{ color: "var(--status-danger)", flexShrink: 0, marginTop: 2 }} />}
                          {sub.advice}
                        </p>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem 1.5rem", fontSize: "0.82rem" }}>
                        {[
                          ["Paycycle Position", `${sub.breakdown.days_since_payday} days after payday`],
                          ["Financial Load", `${Math.round(sub.breakdown.load_factor * 100)}% of salary consumed`],
                          ["Failure History", `${sub.fail_history} failed attempts`],
                          ["Expense Clustering", `$${sub.breakdown.cluster_amount.toLocaleString()} within ±3 days`],
                        ].map(([label, val], i) => (
                          <div key={i} style={{ display: "flex", justifyContent: "space-between", paddingBottom: "0.35rem", borderBottom: "1px solid var(--border-subtle)" }}>
                            <span style={{ color: "var(--text-muted)" }}>{label}</span>
                            <span style={{ fontWeight: 500 }}>{val}</span>
                          </div>
                        ))}
                      </div>
                    </MotionCard>
                  );
                })}

                {results.subscriptions.length === 0 && (
                  <MotionCard hover={false} style={{ textAlign: "center", padding: "3rem 2rem" }}>
                    <Info size={40} style={{ color: "var(--text-muted)", margin: "0 auto 1rem" }} />
                    <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.4rem" }}>No Subscriptions Detected</h3>
                    <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                      We couldn't identify any recurring subscription payments in this statement.
                    </p>
                  </MotionCard>
                )}

                {/* Price Change Detection */}
                {results.price_changes && results.price_changes.length > 0 && (
                  <MotionCard hover={false} delay={0.4} style={{ border: "1px solid var(--accent-gold-border)", background: "var(--accent-gold-light)" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
                      <h2 style={{ fontSize: "1.1rem", fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem", margin: 0 }}>
                        <AlertTriangle size={18} style={{ color: "var(--accent-gold)" }} />
                        Price Change Detection
                      </h2>
                      <Badge variant="warn" style={{ background: "var(--accent-gold)", color: "#fff", fontSize: "0.65rem" }}>CUSUM</Badge>
                    </div>
                    <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                      Structural billing changes detected using Cumulative Sum analysis.
                    </p>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                      {results.price_changes.map((change: any, idx: number) => (
                        <div key={idx} style={{ padding: "0.85rem 1rem", borderRadius: "10px", background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.4rem" }}>
                            <div>
                              <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>{change.subscription}</span>
                              <Badge
                                variant={change.severity === "warning" ? "danger" : "safe"}
                                style={{ marginLeft: "0.5rem", fontSize: "0.6rem" }}
                              >
                                {change.type}
                              </Badge>
                            </div>
                            <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{change.date}</span>
                          </div>
                          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.5rem" }}>{change.description}</p>
                          <div style={{ display: "flex", gap: "1rem", fontSize: "0.82rem" }}>
                            <span><span style={{ color: "var(--text-muted)" }}>Before: </span><span style={{ fontWeight: 500 }}>${change.old_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span></span>
                            <span><span style={{ color: "var(--text-muted)" }}>After: </span><span style={{ fontWeight: 500 }}>${change.new_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span></span>
                            <span style={{ fontWeight: 700, color: change.change_amount > 0 ? "var(--status-danger)" : "var(--status-safe)" }}>
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
