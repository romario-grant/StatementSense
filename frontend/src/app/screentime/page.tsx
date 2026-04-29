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
  if (velocity > 1.05) return <TrendingUp style={{ color: "var(--status-safe)" }} size={14} />;
  if (velocity < 0.95) return <TrendingDown style={{ color: "var(--status-danger)" }} size={14} />;
  return <Minus style={{ color: "var(--text-muted)" }} size={14} />;
};

const sectionDivider: React.CSSProperties = {
  height: "1px",
  background: "var(--border-subtle)",
  border: "none",
  margin: 0,
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
      <main className="container" style={{ paddingTop: "5rem", paddingBottom: "3rem" }}>
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          style={{ marginBottom: "2rem" }}
        >
          <h1 style={{ fontSize: "2rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "0.3rem" }}>
            ScreentimeSense
          </h1>
          <p style={{ color: "var(--text-secondary)" }}>
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
              <MotionCard style={{ maxWidth: "28rem", margin: "0 auto" }} hover={false}>
                <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                  Set Your Baseline
                </h2>
                <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "1.5rem" }}>
                  We calculate &quot;Cost Per Hour&quot; (CPH) and compare it against your hourly wage to judge subscription value.
                </p>

                <form onSubmit={saveSettings} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  {/* Hourly Wage */}
                  <div>
                    <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 500, marginBottom: "0.35rem" }}>
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
                    />
                  </div>

                  {/* Budgeting Style — Custom Dropdown */}
                  <div>
                    <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 500, marginBottom: "0.35rem" }}>
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
                        <div style={{ position: "relative" }}>
                          <button
                            type="button"
                            onClick={() => setDropdownOpen(!dropdownOpen)}
                            style={{
                              width: "100%",
                              padding: "0.7rem 1rem",
                              borderRadius: "10px",
                              border: "1px solid rgba(255,255,255,0.1)",
                              background: "rgba(255,255,255,0.05)",
                              color: "var(--text-primary)",
                              fontSize: "0.9rem",
                              fontWeight: 500,
                              textAlign: "left",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              transition: "border-color 0.2s, background 0.2s",
                              outline: "none",
                            }}
                            onFocus={(e) => (e.currentTarget.style.borderColor = "var(--accent-teal)")}
                            onBlur={(e) => (e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)")}
                          >
                            {selected.label}
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ opacity: 0.5, transform: dropdownOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}>
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
                                style={{
                                  position: "absolute",
                                  top: "100%",
                                  left: 0,
                                  right: 0,
                                  zIndex: 60,
                                  listStyle: "none",
                                  margin: 0,
                                  padding: "0.35rem",
                                  borderRadius: "12px",
                                  background: "rgba(22, 22, 22, 0.95)",
                                  backdropFilter: "blur(20px)",
                                  WebkitBackdropFilter: "blur(20px)",
                                  border: "1px solid rgba(255,255,255,0.1)",
                                  boxShadow: "0 16px 40px rgba(0,0,0,0.5)",
                                  overflow: "hidden",
                                }}
                              >
                                {options.map((opt) => (
                                  <li
                                    key={opt.value}
                                    onClick={() => {
                                      setGlobalSettings({ ...globalSettings, style_multiplier: opt.value });
                                      setDropdownOpen(false);
                                    }}
                                    style={{
                                      padding: "0.6rem 0.85rem",
                                      borderRadius: "8px",
                                      fontSize: "0.88rem",
                                      cursor: "pointer",
                                      color: opt.value === globalSettings.style_multiplier ? "#ffffff" : "var(--text-secondary)",
                                      background: opt.value === globalSettings.style_multiplier ? "rgba(255,255,255,0.08)" : "transparent",
                                      transition: "background 0.15s, color 0.15s",
                                    }}
                                    onMouseEnter={(e) => {
                                      e.currentTarget.style.background = "rgba(255,255,255,0.06)";
                                      e.currentTarget.style.color = "#ffffff";
                                    }}
                                    onMouseLeave={(e) => {
                                      e.currentTarget.style.background = opt.value === globalSettings.style_multiplier ? "rgba(255,255,255,0.08)" : "transparent";
                                      e.currentTarget.style.color = opt.value === globalSettings.style_multiplier ? "#ffffff" : "var(--text-secondary)";
                                    }}
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
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      padding: "0.75rem 1rem",
                      borderRadius: "12px",
                      background: "var(--bg-secondary)",
                    }}
                  >
                    <label style={{ position: "relative", width: "2.75rem", height: "1.5rem", display: "inline-block", flexShrink: 0 }}>
                      <input
                        type="checkbox"
                        checked={globalSettings.is_student}
                        onChange={(e) => setGlobalSettings({ ...globalSettings, is_student: e.target.checked })}
                        style={{ opacity: 0, width: 0, height: 0, position: "absolute" }}
                      />
                      <span
                        style={{
                          position: "absolute",
                          cursor: "pointer",
                          top: 0,
                          left: 0,
                          right: 0,
                          bottom: 0,
                          background: globalSettings.is_student ? "var(--accent-teal)" : "var(--bg-tertiary)",
                          borderRadius: "1rem",
                          transition: "0.3s",
                        }}
                      >
                        <span
                          style={{
                            position: "absolute",
                            height: "1.1rem",
                            width: "1.1rem",
                            left: globalSettings.is_student ? "1.45rem" : "0.2rem",
                            bottom: "0.2rem",
                            background: "#fff",
                            borderRadius: "50%",
                            transition: "0.3s",
                          }}
                        />
                      </span>
                    </label>
                    <div>
                      <span style={{ fontSize: "0.85rem", fontWeight: 500 }}>I&apos;m a Student</span>
                      <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.1rem" }}>
                        Scans Google Calendar for exams &amp; suggests pausing entertainment subscriptions.
                      </p>
                    </div>
                  </div>

                  <button type="submit" className="btn-primary" style={{ marginTop: "0.5rem", padding: "0.75rem" }}>
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
              style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "1.5rem" }}
            >
              {/* ── Left: Add Subscription Form ── */}
              <div>
                <MotionCard hover={false}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "1rem", marginBottom: "1.25rem" }}>
                    <h2 style={{ fontSize: "1.1rem", fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem", margin: 0 }}>
                      <Plus size={18} style={{ color: "var(--accent-teal)" }} /> Add Subscription
                    </h2>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      ${(parseFloat(globalSettings.user_wage || "0") * globalSettings.style_multiplier).toFixed(2)}/hr
                    </span>
                  </div>
                  <hr style={sectionDivider} />

                  <form onSubmit={addSubscription} style={{ display: "flex", flexDirection: "column", gap: "1.25rem", marginTop: "1.25rem" }}>
                    {/* App Name */}
                    <div>
                      <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 500, marginBottom: "0.35rem" }}>App Name</label>
                      <input required type="text" placeholder="e.g. Netflix, Duolingo, ChatGPT" value={formData.app_name} onChange={(e) => setFormData({ ...formData, app_name: e.target.value })} />
                    </div>

                    {/* Cost + Months row */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                      <div>
                        <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 500, marginBottom: "0.35rem" }}>Cost ($)</label>
                        <input required type="number" step="0.01" placeholder="14.99" value={formData.cost} onChange={(e) => setFormData({ ...formData, cost: e.target.value })} />
                      </div>
                      <div>
                        <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 500, marginBottom: "0.35rem" }}>Months</label>
                        <input required type="number" min="1" value={formData.months_subscribed} onChange={(e) => setFormData({ ...formData, months_subscribed: e.target.value })} />
                      </div>
                    </div>

                    {/* Weekly Hours */}
                    <div>
                      <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.5rem" }}>Screen Time (Hours per week)</label>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "1rem", padding: "1rem", borderRadius: "14px", background: "var(--bg-secondary)" }}>
                        {(
                          [
                            ["Wk 1", "w1"],
                            ["Wk 2", "w2"],
                            ["Wk 3", "w3"],
                            ["Wk 4", "w4"],
                          ] as const
                        ).map(([label, key]) => (
                          <div key={key}>
                            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>{label}</span>
                            <input
                              required
                              type="number"
                              step="0.1"
                              min="0"
                              placeholder="hrs"
                              style={{ width: "100%", minWidth: "3.5rem", textAlign: "center" }}
                              value={formData[key]}
                              onChange={(e) => setFormData({ ...formData, [key]: e.target.value })}
                            />
                          </div>
                        ))}
                      </div>
                    </div>

                    <button type="submit" className="btn-primary" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem", padding: "0.75rem" }}>
                      <Plus size={16} /> Add to Queue
                    </button>
                  </form>
                </MotionCard>
              </div>

              {/* ── Right: Queue List ── */}
              <div>
                <MotionCard hover={false} style={{ minHeight: "400px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                    <h2 style={{ fontSize: "1.1rem", fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem", margin: 0 }}>
                      <Layers size={18} style={{ color: "var(--accent-teal)" }} /> Subscription Queue
                    </h2>
                    <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                      {subscriptions.length} subscription{subscriptions.length !== 1 ? "s" : ""}
                    </span>
                  </div>
                  <hr style={sectionDivider} />

                  {/* Error Banner */}
                  {error && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      style={{ display: "flex", gap: "0.5rem", alignItems: "center", padding: "0.75rem 1rem", background: "var(--status-danger-bg)", color: "var(--status-danger)", borderRadius: "10px", marginTop: "1rem", fontSize: "0.85rem" }}
                    >
                      <AlertTriangle size={16} />
                      <span>{error}</span>
                    </motion.div>
                  )}

                  {subscriptions.length === 0 ? (
                    /* Empty State */
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "4rem 2rem", opacity: 0.4 }}>
                      <Clock size={48} style={{ color: "var(--text-muted)", marginBottom: "1rem" }} />
                      <p style={{ fontSize: "1rem", fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--text-muted)" }}>No Subscriptions Yet</p>
                      <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", textAlign: "center", maxWidth: "18rem", marginTop: "0.5rem" }}>
                        Add subscriptions using the form to build your analysis queue.
                      </p>
                    </div>
                  ) : (
                    /* Queue Items + Analyze Button */
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "1rem" }}>
                      {subscriptions.map((sub, i) => (
                        <div
                          key={sub.id}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            padding: "1rem 1.25rem",
                            borderRadius: "14px",
                            background: "var(--bg-secondary)",
                            transition: "all 0.2s ease",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                            <span
                              style={{
                                width: "2rem",
                                height: "2rem",
                                borderRadius: "10px",
                                background: "var(--accent-teal-light)",
                                color: "var(--accent-teal)",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                fontSize: "0.8rem",
                                fontWeight: 700,
                              }}
                            >
                              {i + 1}
                            </span>
                            <div>
                              <p style={{ fontWeight: 600, fontSize: "0.85rem" }}>{sub.app_name}</p>
                              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                ${sub.cost}/billing • {sub.months_subscribed}mo •{" "}
                                {sub.weekly_hours.reduce((a, b) => a + b, 0).toFixed(1)} hrs total
                              </p>
                            </div>
                          </div>
                          <button
                            onClick={() => removeSubscription(sub.id)}
                            style={{ background: "none", border: "none", padding: "0.4rem", color: "var(--status-danger)", opacity: 0.6, cursor: "pointer" }}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      ))}

                      <button
                        onClick={handleAnalyzeBatch}
                        disabled={loading}
                        className="btn-primary"
                        style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem", padding: "0.75rem", marginTop: "1rem" }}
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
                      <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", textAlign: "center", marginTop: "0.25rem" }}>
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
              style={{ display: "flex", flexDirection: "column", gap: "2rem" }}
            >
              {/* ── Summary Bar ── */}
              <MotionCard hover={false} style={{ background: "var(--bg-primary)" }}>
                <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
                  <div>
                    <h2 style={{ fontSize: "1.25rem", fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                      <BarChart3 size={20} style={{ color: "var(--accent-teal)" }} /> Analysis Complete
                    </h2>
                    <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                      {batchResults.count} subscription{batchResults.count !== 1 ? "s" : ""} analyzed in parallel
                    </p>
                  </div>
                  <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
                    {batchResults.portfolio?.saturated_categories > 0 && (
                      <div style={{ textAlign: "right" }}>
                        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Portfolio Savings</p>
                        <p style={{ fontWeight: 700, color: "var(--status-safe)", fontSize: "1.25rem" }}>
                          ${batchResults.portfolio.total_potential_savings_annual.toFixed(2)}/yr
                        </p>
                      </div>
                    )}
                    <button onClick={resetAll} style={{ color: "var(--accent-teal)", fontSize: "0.85rem", background: "none", border: "none" }}>
                      ← New Analysis
                    </button>
                  </div>
                </div>
              </MotionCard>

              {/* ── Portfolio Analysis (Category Saturation) ── */}
              {batchResults.portfolio?.category_insights?.length > 0 && (
                <MotionCard hover={false} delay={0.1} style={{ borderTop: "3px solid var(--accent-gold)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
                    <Layers size={20} style={{ color: "var(--accent-gold)" }} />
                    <h3 style={{ fontWeight: 700, margin: 0 }}>Portfolio Analysis — Category Saturation</h3>
                  </div>
                  <hr style={sectionDivider} />

                  <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", marginTop: "1rem" }}>
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    {batchResults.portfolio.category_insights.map((insight: any, idx: number) => (
                      <motion.div
                        key={idx}
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, delay: 0.15 + idx * 0.1 }}
                        style={{ padding: "1.25rem", borderRadius: "16px", background: "var(--bg-secondary)" }}
                      >
                        {/* Category Header */}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <Badge variant="warn" style={{ fontSize: "0.7rem", fontWeight: 700 }}>
                              {insight.subscription_count} SUBSCRIPTIONS
                            </Badge>
                            <h4 style={{ fontWeight: 700, margin: 0, textTransform: "capitalize" }}>{insight.category_label}</h4>
                          </div>
                          <span style={{ fontSize: "0.9rem", fontWeight: 700 }}>
                            ${insight.total_monthly_cost.toFixed(2)}/mo
                          </span>
                        </div>

                        {/* Ranked Subscriptions Table */}
                        <div style={{ borderRadius: "12px", overflow: "hidden", border: "1px solid var(--border-subtle)", background: "var(--bg-primary)" }}>
                          {/* Table Header */}
                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns: "1fr 1fr 1fr 1fr",
                              padding: "0.75rem",
                              backgroundColor: "var(--bg-secondary)",
                              fontSize: "0.7rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: "0.06em",
                              color: "var(--text-muted)",
                            }}
                          >
                            <span>Rank</span>
                            <span>Subscription</span>
                            <span style={{ textAlign: "right" }}>CPH</span>
                            <span style={{ textAlign: "right" }}>Cost</span>
                          </div>

                          {/* Table Rows — staggered entrance */}
                          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                          {insight.ranked_subscriptions.map((sub: any, rowIdx: number) => (
                            <motion.div
                              key={sub.app_name}
                              initial={{ opacity: 0, x: -8 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ duration: 0.3, delay: 0.25 + idx * 0.1 + rowIdx * 0.08 }}
                              style={{
                                display: "grid",
                                gridTemplateColumns: "1fr 1fr 1fr 1fr",
                                padding: "0.75rem",
                                alignItems: "center",
                                borderTop: "1px solid var(--border-subtle)",
                                backgroundColor: sub.is_best_value
                                  ? "var(--status-safe-bg)"
                                  : sub.is_worst_value
                                  ? "var(--status-danger-bg)"
                                  : "transparent",
                              }}
                            >
                              <span
                                style={{
                                  fontSize: "0.85rem",
                                  fontWeight: 700,
                                  color: sub.is_best_value
                                    ? "var(--status-safe)"
                                    : sub.is_worst_value
                                    ? "var(--status-danger)"
                                    : "inherit",
                                }}
                              >
                                #{sub.rank} {sub.is_best_value ? "👑" : sub.is_worst_value ? "⚠️" : ""}
                              </span>
                              <span style={{ fontSize: "0.85rem", fontWeight: 500 }}>{sub.app_name}</span>
                              <span
                                style={{
                                  fontSize: "0.85rem",
                                  textAlign: "right",
                                  fontWeight: 500,
                                  color: sub.is_best_value
                                    ? "var(--status-safe)"
                                    : sub.is_worst_value
                                    ? "var(--status-danger)"
                                    : "inherit",
                                }}
                              >
                                ${sub.cph.toFixed(2)}/hr
                              </span>
                              <span style={{ fontSize: "0.85rem", textAlign: "right", color: "var(--text-muted)" }}>
                                ${sub.monthly_cost.toFixed(2)}/mo
                              </span>
                            </motion.div>
                          ))}
                        </div>

                        {/* Savings Callout Cards */}
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "1rem", marginTop: "0.75rem" }}>
                          <motion.div
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.35, delay: 0.4 + idx * 0.1 }}
                            style={{
                              flex: 1,
                              minWidth: "200px",
                              padding: "0.75rem 1rem",
                              borderRadius: "12px",
                              background: "var(--bg-primary)",
                              border: "1px solid var(--border-subtle)",
                            }}
                          >
                            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                              Drop {insight.worst_value.name}
                            </p>
                            <p style={{ fontWeight: 700, color: "var(--status-safe)" }}>
                              ${insight.savings_drop_worst.toFixed(2)}/mo{" "}
                              <span style={{ fontSize: "0.75rem", fontWeight: 500, color: "var(--text-muted)" }}>
                                (${insight.savings_drop_worst_annual.toFixed(2)}/yr)
                              </span>
                            </p>
                          </motion.div>

                          {insight.subscription_count > 2 && (
                            <motion.div
                              initial={{ opacity: 0, y: 8 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ duration: 0.35, delay: 0.5 + idx * 0.1 }}
                              style={{
                                flex: 1,
                                minWidth: "200px",
                                padding: "0.75rem 1rem",
                                borderRadius: "12px",
                                background: "var(--bg-primary)",
                                border: "1px solid var(--border-subtle)",
                              }}
                            >
                              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                Keep only {insight.best_value.name}
                              </p>
                              <p style={{ fontWeight: 700, color: "var(--status-safe)" }}>
                                ${insight.savings_keep_best_only.toFixed(2)}/mo{" "}
                                <span style={{ fontSize: "0.75rem", fontWeight: 500, color: "var(--text-muted)" }}>
                                  (${insight.savings_keep_best_only_annual.toFixed(2)}/yr)
                                </span>
                              </p>
                            </motion.div>
                          )}
                        </div>

                        {/* Recommendation */}
                        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.75rem", fontStyle: "italic" }}>
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
                    style={{
                      background: "rgba(97, 205, 255, 0.05)",
                      border: "1px solid rgba(97, 205, 255, 0.2)",
                      padding: "1.5rem",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}>
                      <div style={{ flex: 1 }}>
                        {/* Title */}
                        <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.25rem" }}>
                          Exam Season Detected
                        </h3>
                        <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.75rem" }}>
                          {batchResults.exam_alert.message}
                        </p>

                        {/* Upcoming Exams */}
                        {batchResults.exam_alert.exams.length > 0 && (
                          <div style={{ marginBottom: "0.75rem" }}>
                            <p
                              style={{
                                fontSize: "0.7rem",
                                fontWeight: 700,
                                textTransform: "uppercase",
                                letterSpacing: "0.06em",
                                color: "var(--text-muted)",
                                marginBottom: "0.4rem",
                              }}
                            >
                              Upcoming Exams
                            </p>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                              {batchResults.exam_alert.exams.map((exam: any, i: number) => (
                                <motion.span
                                  key={i}
                                  initial={{ opacity: 0, scale: 0.9 }}
                                  animate={{ opacity: 1, scale: 1 }}
                                  transition={{ duration: 0.3, delay: 0.35 + i * 0.06 }}
                                  style={{
                                    fontSize: "0.75rem",
                                    fontWeight: 500,
                                    padding: "0.25rem 0.6rem",
                                    borderRadius: "0.5rem",
                                    background: "rgba(97, 205, 255, 0.12)",
                                    color: "var(--accent-teal)",
                                  }}
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
                            <p
                              style={{
                                fontSize: "0.7rem",
                                fontWeight: 700,
                                textTransform: "uppercase",
                                letterSpacing: "0.06em",
                                color: "var(--text-muted)",
                                marginBottom: "0.35rem",
                              }}
                            >
                              Consider Pausing
                            </p>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                              {batchResults.exam_alert.pausable_subscriptions.map((sub: any, i: number) => (
                                <motion.span
                                  key={i}
                                  initial={{ opacity: 0, scale: 0.9 }}
                                  animate={{ opacity: 1, scale: 1 }}
                                  transition={{ duration: 0.3, delay: 0.4 + i * 0.06 }}
                                >
                                  <Badge variant="warn" style={{ fontSize: "0.72rem" }}>
                                    {sub.name} (${sub.monthly_cost.toFixed(2)}/mo)
                                  </Badge>
                                </motion.span>
                              ))}
                              <motion.span
                                initial={{ opacity: 0, scale: 0.9 }}
                                animate={{ opacity: 1, scale: 1 }}
                                transition={{ duration: 0.3, delay: 0.55 }}
                              >
                                <Badge variant="safe" style={{ fontSize: "0.72rem", fontWeight: 700 }}>
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
                  style={{ fontWeight: 700, fontSize: "1.1rem", marginBottom: "1rem" }}
                >
                  Individual Analysis
                </motion.h3>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  {batchResults.results.map((result: any, i: number) => {
                    const actionVariant = getActionColor(result.action);
                    const borderColor =
                      actionVariant === "safe"
                        ? "var(--status-safe)"
                        : actionVariant === "danger"
                        ? "var(--status-danger)"
                        : "var(--status-warn)";
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
                        className="card"
                        onClick={() => setExpandedResult(isExpanded ? null : i)}
                        style={{
                          padding: "1.25rem",
                          borderLeft: `4px solid ${borderColor}`,
                          cursor: "pointer",
                          transition: "transform 0.2s ease, box-shadow 0.2s ease",
                        }}
                        whileHover={{
                          y: -2,
                          boxShadow: "0 6px 24px rgba(0,0,0,0.25)",
                          transition: { duration: 0.2 },
                        }}
                      >
                        {/* Card Header: Name + Action + VRS + CPH */}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                          <div>
                            <h4 style={{ fontWeight: 700, marginBottom: "0.25rem" }}>{result.app_name}</h4>
                            <Badge
                              variant={actionVariant}
                              style={{ fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.08em" }}
                            >
                              {result.action}
                            </Badge>
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                            {/* Value Risk Score Circle */}
                            {result.value_risk_score !== undefined && (
                              <div style={{ textAlign: "center" }}>
                                <div
                                  style={{
                                    width: "3rem",
                                    height: "3rem",
                                    borderRadius: "50%",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    fontSize: "1rem",
                                    fontWeight: 800,
                                    background:
                                      result.value_risk_score > 70
                                        ? "var(--status-safe-bg)"
                                        : result.value_risk_score >= 40
                                        ? "var(--status-warn-bg)"
                                        : "var(--status-danger-bg)",
                                    color:
                                      result.value_risk_score > 70
                                        ? "var(--status-safe)"
                                        : result.value_risk_score >= 40
                                        ? "var(--status-warn)"
                                        : "var(--status-danger)",
                                    border: `2px solid ${
                                      result.value_risk_score > 70
                                        ? "var(--status-safe)"
                                        : result.value_risk_score >= 40
                                        ? "var(--status-warn)"
                                        : "var(--status-danger)"
                                    }`,
                                  }}
                                >
                                  {result.value_risk_score}
                                </div>
                                <p
                                  style={{
                                    fontSize: "0.55rem",
                                    color: "var(--text-muted)",
                                    marginTop: "0.15rem",
                                    fontWeight: 600,
                                    textTransform: "uppercase",
                                  }}
                                >
                                  VRS
                                </p>
                              </div>
                            )}
                            {/* CPH + Burden */}
                            <div style={{ textAlign: "right" }}>
                              <p
                                style={{
                                  fontSize: "0.85rem",
                                  fontWeight: 700,
                                  color:
                                    result.math.cph > wageThreshold
                                      ? "var(--status-danger)"
                                      : "var(--status-safe)",
                                }}
                              >
                                ${result.math.cph.toFixed(2)}/{result.is_presence ? "day" : "hr"}
                              </p>
                              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                ${result.math.personal_burden.toFixed(2)}/mo
                              </p>
                            </div>
                          </div>
                        </div>

                        {/* Reason */}
                        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
                          {result.reason}
                        </p>

                        {/* Velocity Row */}
                        {!result.is_presence && (
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "1rem",
                              fontSize: "0.75rem",
                              color: "var(--text-muted)",
                              marginTop: "0.75rem",
                              paddingTop: "0.75rem",
                              borderTop: "1px solid var(--border-subtle)",
                              flexWrap: "wrap",
                            }}
                          >
                            <span style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                              {getVelocityIcon(result.math.velocity)} {result.math.velocity.toFixed(2)}{" "}
                              {getVelocityLabel(result.math.velocity)}
                            </span>
                            <span>
                              {result.math.raw_hours.toFixed(1)} hrs • {result.math.weight}x weight
                            </span>
                            <span>Conf: {result.confidence_label}</span>
                            {result.value_risk_label && (
                              <span
                                style={{
                                  fontWeight: 600,
                                  color:
                                    result.value_risk_score > 70
                                      ? "var(--status-safe)"
                                      : result.value_risk_score >= 40
                                      ? "var(--status-warn)"
                                      : "var(--status-danger)",
                                }}
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
                              style={{ overflow: "hidden" }}
                            >
                              <div
                                style={{
                                  marginTop: "1rem",
                                  paddingTop: "1rem",
                                  borderTop: "1px solid var(--border-subtle)",
                                  display: "grid",
                                  gridTemplateColumns: "1fr 1fr",
                                  gap: "0.75rem",
                                }}
                              >
                                {/* Math Breakdown */}
                                <div>
                                  <h5
                                    style={{
                                      fontSize: "0.7rem",
                                      fontWeight: 700,
                                      textTransform: "uppercase",
                                      letterSpacing: "0.06em",
                                      color: "var(--text-muted)",
                                      marginBottom: "0.5rem",
                                    }}
                                  >
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
                                      style={{
                                        display: "flex",
                                        justifyContent: "space-between",
                                        fontSize: "0.78rem",
                                        paddingBottom: "0.3rem",
                                      }}
                                    >
                                      <span style={{ color: "var(--text-muted)" }}>{label}</span>
                                      <span style={{ fontWeight: 500 }}>{val}</span>
                                    </div>
                                  ))}
                                </div>

                                {/* AI Classification */}
                                <div>
                                  <h5
                                    style={{
                                      fontSize: "0.7rem",
                                      fontWeight: 700,
                                      textTransform: "uppercase",
                                      letterSpacing: "0.06em",
                                      color: "var(--text-muted)",
                                      marginBottom: "0.5rem",
                                    }}
                                  >
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
                                      style={{
                                        display: "flex",
                                        justifyContent: "space-between",
                                        fontSize: "0.78rem",
                                        paddingBottom: "0.3rem",
                                      }}
                                    >
                                      <span style={{ color: "var(--text-muted)" }}>{label}</span>
                                      <span style={{ fontWeight: 500, textTransform: "capitalize" }}>
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
                                  style={{
                                    marginTop: "0.75rem",
                                    padding: "0.75rem",
                                    borderRadius: "10px",
                                    background: "var(--bg-secondary)",
                                  }}
                                >
                                  <p style={{ fontSize: "0.78rem", fontWeight: 700, marginBottom: "0.35rem" }}>
                                    <DollarSign
                                      size={12}
                                      style={{ display: "inline", verticalAlign: "middle", marginRight: "0.2rem" }}
                                    />
                                    Best Plan:{" "}
                                    <span style={{ textTransform: "capitalize", color: "var(--accent-gold)" }}>
                                      {result.best_plan}
                                    </span>
                                  </p>
                                  <div style={{ display: "flex", gap: "0.75rem", fontSize: "0.75rem" }}>
                                    {Object.entries(result.breakeven_info?.plan_costs_npv || {}).map(
                                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                                      ([plan, cost]: [string, any]) => (
                                        <span
                                          key={plan}
                                          style={{
                                            fontWeight: plan === result.best_plan ? 700 : 400,
                                            color:
                                              plan === result.best_plan
                                                ? "var(--text-primary)"
                                                : "var(--text-muted)",
                                          }}
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
