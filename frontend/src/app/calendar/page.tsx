"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Calendar as CalendarIcon, MapPin, Plus, Trash2, Plane, Activity, CheckCircle, AlertTriangle, Search } from "lucide-react";
import Navbar from "@/components/Navbar";
import MotionCard from "@/components/MotionCard";
import Badge from "@/components/Badge";

interface SubInput { id: number; name: string; cost: string; }

export default function CalendarSensePage() {
  const [homeLocation, setHomeLocation] = useState("Kingston, Jamaica");
  const [subscriptions, setSubscriptions] = useState<SubInput[]>([{ id: 1, name: "", cost: "" }]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [result, setResult] = useState<any>(null);

  const handleAddSub = () => setSubscriptions([...subscriptions, { id: Date.now(), name: "", cost: "" }]);
  const handleRemoveSub = (id: number) => setSubscriptions(subscriptions.filter(s => s.id !== id));
  const handleChangeSub = (id: number, field: string, value: string) => setSubscriptions(subscriptions.map(s => s.id === id ? { ...s, [field]: value } : s));

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!homeLocation) return setError("Home location is required");
    const validSubs = subscriptions.filter(s => s.name.trim() && s.cost);
    if (validSubs.length === 0) return setError("Please add at least one subscription");
    setLoading(true); setError(null); setResult(null);
    try {
      const res = await fetch("/api/calendar/analyze", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ home_location: homeLocation, subscriptions: validSubs.map(s => ({ name: s.name, cost: parseFloat(s.cost) })) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Analysis failed");
      setResult(data);
    } catch (err) { setError(err instanceof Error ? err.message : "An error occurred"); }
    finally { setLoading(false); }
  };

  const divider: React.CSSProperties = { height: "1px", background: "var(--border-subtle)", border: "none", margin: 0 };

  return (
    <>
      <Navbar />
      <main className="container" style={{ paddingTop: "5rem", paddingBottom: "3rem" }}>
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} style={{ marginBottom: "2rem" }}>
          <h1 style={{ fontSize: "2rem", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "0.3rem" }}>CalendarSense</h1>
          <p style={{ color: "var(--text-secondary)" }}>Pause local subscriptions while traveling. Connects to your Google Calendar to detect travel periods.</p>
        </motion.div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "1.5rem" }}>
          {/* ═══ INPUT COLUMN ═══ */}
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <MotionCard hover={false}>
              <h2 style={{ fontSize: "1.15rem", fontWeight: 700, marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <MapPin size={18} style={{ color: "var(--accent-teal)" }} /> Travel Details
              </h2>
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 500, marginBottom: "0.35rem" }}>Your Home Location</label>
                <input type="text" value={homeLocation} onChange={e => setHomeLocation(e.target.value)} placeholder="e.g. Kingston, Jamaica" />
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Used to identify which subscriptions are &quot;local&quot; to you.</p>
              </div>
            </MotionCard>

            <MotionCard hover={false} delay={0.05}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                <h2 style={{ fontSize: "1.15rem", fontWeight: 700, margin: 0 }}>Subscriptions</h2>
                <button type="button" onClick={handleAddSub} style={{ display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.8rem", padding: "0.3rem 0.75rem", color: "var(--accent-teal)", backgroundColor: "var(--accent-teal-light)", borderRadius: "980px", border: "none" }}>
                  <Plus size={14} /> Add
                </button>
              </div>
              <hr style={divider} />
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "1rem" }}>
                {subscriptions.map((sub, index) => (
                  <div key={sub.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ color: "var(--text-muted)", fontSize: "0.75rem", width: "1rem" }}>{index + 1}.</span>
                    <input type="text" placeholder="Name" style={{ flex: 1, fontSize: "0.9rem", padding: "0.5rem 0.75rem" }} value={sub.name} onChange={e => handleChangeSub(sub.id, "name", e.target.value)} />
                    <input type="number" step="0.01" placeholder="$ Cost" style={{ width: "6rem", fontSize: "0.9rem", padding: "0.5rem 0.75rem" }} value={sub.cost} onChange={e => handleChangeSub(sub.id, "cost", e.target.value)} />
                    <button onClick={() => handleRemoveSub(sub.id)} style={{ padding: "0.5rem", color: "var(--status-danger)", background: "none", border: "none", borderRadius: "8px", cursor: "pointer" }}><Trash2 size={15} /></button>
                  </div>
                ))}
                {subscriptions.length === 0 && <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", textAlign: "center", padding: "1rem 0" }}>No subscriptions added.</p>}
              </div>
            </MotionCard>

            {error && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} style={{ display: "flex", gap: "0.5rem", alignItems: "center", padding: "0.75rem 1rem", background: "var(--status-danger-bg)", color: "var(--status-danger)", borderRadius: "14px", fontSize: "0.85rem" }}>
                <AlertTriangle size={16} /> <span>{error}</span>
              </motion.div>
            )}

            <MotionCard hover={false} delay={0.1} style={{ textAlign: "center", background: "rgba(97, 205, 255, 0.04)", border: "1px solid rgba(97, 205, 255, 0.12)" }}>
              <CalendarIcon size={28} style={{ color: "var(--accent-teal)", margin: "0 auto 0.75rem" }} />
              <h3 style={{ fontWeight: 700, fontSize: "1rem", marginBottom: "0.5rem" }}>Connect &amp; Scan</h3>
              <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "1rem" }}>Securely analyze the next 6 months of your Google Calendar.</p>
              <button onClick={handleAnalyze} disabled={loading} className="btn-primary" style={{ width: "100%", padding: "0.75rem", display: "flex", justifyContent: "center", alignItems: "center", gap: "0.5rem", fontWeight: 700 }}>
                {loading ? (<><Activity size={18} className="animate-spin" /> Analyzing...</>) : "Scan Calendar for Travel"}
              </button>
            </MotionCard>
          </div>

          {/* ═══ RESULTS COLUMN ═══ */}
          <div>
            <AnimatePresence mode="wait">
              {!result ? (
                <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                  <MotionCard hover={false} style={{ height: "100%", minHeight: "400px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", border: "none" }}>
                    <motion.div animate={{ y: [0, -8, 0] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
                      <Plane size={48} style={{ color: "var(--accent-teal)", marginBottom: "1rem", opacity: 0.5 }} />
                    </motion.div>
                    <p style={{ fontSize: "1rem", fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--text-muted)" }}>Ready to Scan</p>
                    <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", textAlign: "center", maxWidth: "18rem", marginTop: "0.5rem" }}>Enter your details and connect your calendar to find travel overlaps.</p>
                  </MotionCard>
                </motion.div>
              ) : (
                <motion.div key="results" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>

                  {/* SUMMARY STATS */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "1rem" }}>
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    {([["Events", result.events_scanned, null], ["Trips", result.away_periods.length, "var(--status-safe)"], ["Local", result.local_count || 0, "var(--status-warn)"], ["Savings", `$${result.total_savings.toFixed(2)}`, "var(--accent-gold)"]] as [string, any, string | null][]).map(([label, value, color], i) => (
                      <MotionCard key={label} hover={false} delay={i * 0.06} style={{ textAlign: "center", padding: "1.25rem 0.75rem" }}>
                        <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600, marginBottom: "0.35rem" }}>{label}</p>
                        <p style={{ fontSize: "1.5rem", fontWeight: 700, color: color || "var(--text-primary)" }}>{value}</p>
                      </MotionCard>
                    ))}
                  </div>

                  {/* EVENTS PREVIEW */}
                  {result.events_preview && result.events_preview.length > 0 && (
                    <MotionCard hover={false} delay={0.15}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
                        <h3 style={{ fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem", margin: 0 }}><CalendarIcon size={18} style={{ color: "var(--accent-teal)" }} /> Events Scanned</h3>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{result.events_scanned} total</span>
                      </div>
                      <hr style={divider} />
                      <div style={{ marginTop: "0.5rem" }}>
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        {result.events_preview.map((ev: any, i: number) => (
                          <div key={i} style={{ display: "flex", gap: "0.75rem", fontSize: "0.85rem", padding: "0.5rem 0", borderBottom: "1px solid var(--border-subtle)" }}>
                            <span style={{ color: "var(--text-muted)", fontFamily: "monospace", fontSize: "0.7rem", width: "5rem", flexShrink: 0, paddingTop: "0.15rem" }}>[{ev.date}]</span>
                            <span style={{ fontWeight: 500 }}>{ev.summary}</span>
                            {ev.location && <span style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginLeft: "auto" }}>📍 {ev.location}</span>}
                          </div>
                        ))}
                        {result.events_scanned > 15 && <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", textAlign: "center", marginTop: "0.5rem" }}>... and {result.events_scanned - 15} more events</p>}
                      </div>
                    </MotionCard>
                  )}

                  {/* TRAVEL DETECTION */}
                  <MotionCard hover={false} delay={0.2}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
                      <h3 style={{ fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem", margin: 0 }}><Plane size={18} style={{ color: "var(--accent-teal)" }} /> Travel Detection</h3>
                      <Badge variant="teal" style={{ fontSize: "0.65rem" }}>Powered by Gemini AI</Badge>
                    </div>
                    <hr style={divider} />
                    {result.away_periods.length === 0 ? (
                      <div style={{ textAlign: "center", padding: "2rem 0" }}><p style={{ color: "var(--text-muted)" }}>No travel detected in the next 6 months.</p></div>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "1rem" }}>
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        {result.away_periods.map((away: any, i: number) => {
                          const days = Math.ceil((new Date(away.return_date).getTime() - new Date(away.departure_date).getTime()) / (1000 * 60 * 60 * 24));
                          return (
                            <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 + i * 0.08 }} style={{ padding: "1.25rem", borderRadius: "14px", background: "var(--bg-secondary)" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.5rem" }}>
                                <p style={{ fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                  <span>{away.confidence === "high" ? "🟢" : away.confidence === "medium" ? "🟡" : "🔴"}</span> {away.reason}
                                </p>
                                <Badge variant={away.confidence === "high" ? "safe" : "warn"} style={{ textTransform: "capitalize", fontSize: "0.65rem" }}>{away.confidence} confidence</Badge>
                              </div>
                              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem", fontSize: "0.85rem", marginTop: "0.75rem" }}>
                                <div><span style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Dates</span><span style={{ fontWeight: 500 }}>{away.departure_date} → {away.return_date}</span></div>
                                <div><span style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Destination</span><span style={{ fontWeight: 500, display: "flex", alignItems: "center", gap: "0.25rem" }}><MapPin size={12} /> {away.destination || "Unknown"}</span></div>
                                <div><span style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block" }}>Duration</span><span style={{ fontWeight: 500 }}>{days} days ({Math.ceil(days / 30)} months)</span></div>
                              </div>
                              {away.trigger_type && <div style={{ marginTop: "0.5rem" }}><span style={{ fontSize: "0.7rem", padding: "0.15rem 0.5rem", borderRadius: "980px", background: "var(--bg-tertiary)", textTransform: "capitalize" }}>{away.trigger_type}</span></div>}
                            </motion.div>
                          );
                        })}
                      </div>
                    )}
                  </MotionCard>

                  {/* SUBSCRIPTION CLASSIFICATION */}
                  <MotionCard hover={false} delay={0.25}>
                    <h3 style={{ fontWeight: 700, display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}><Search size={18} style={{ color: "var(--accent-teal)" }} /> Subscription Classification</h3>
                    <hr style={divider} />
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "1rem" }}>
                      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                      {result.processed_subscriptions.map((sub: any, i: number) => (
                        <motion.div key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 + i * 0.07 }} style={{ padding: "1.25rem", borderRadius: "14px", backgroundColor: sub.is_local ? "var(--accent-gold-light)" : "var(--bg-secondary)", border: sub.is_local ? "1px solid var(--accent-gold-border)" : "1px solid transparent" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                            <span style={{ fontWeight: 700, fontSize: "1.1rem" }}>{sub.name}</span>
                            <Badge variant={sub.is_local ? "danger" : "safe"} style={{ fontWeight: 700, fontSize: "0.65rem" }}>{sub.is_local ? "📍 LOCAL" : "🌍 GLOBAL"}</Badge>
                          </div>
                          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.75rem" }}>{sub.reason}</p>
                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem 1.5rem", fontSize: "0.82rem" }}>
                            {([["Location Type", sub.location_type?.replace("_", " ")], ["Monthly Cost", `$${(sub.monthly_cost || 0).toFixed(2)}`], ["Can Pause", sub.can_pause ? "✓ Yes" : "✗ No"], ["Can Cancel & Rejoin", sub.can_cancel_and_rejoin ? "✓ Yes" : "✗ No"]] as [string, string][]).map(([label, val]) => (
                              <div key={label} style={{ display: "flex", justifyContent: "space-between", paddingBottom: "0.35rem", borderBottom: "1px solid var(--border-subtle)" }}>
                                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{label}</span>
                                <span style={{ fontWeight: 500, textTransform: "capitalize" }}>{val || "N/A"}</span>
                              </div>
                            ))}
                            {sub.cancellation_penalty > 0 && (
                              <div style={{ display: "flex", justifyContent: "space-between", paddingBottom: "0.35rem", borderBottom: "1px solid var(--border-subtle)" }}>
                                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Penalty</span>
                                <span style={{ fontWeight: 500, color: "var(--status-danger)" }}>${sub.cancellation_penalty}</span>
                              </div>
                            )}
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </MotionCard>

                  {/* SAVINGS PLAN */}
                  {result.recommendations.length > 0 && (
                    <MotionCard hover={false} delay={0.3} style={{ border: "1px solid rgba(97, 205, 255, 0.15)" }}>
                      <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "1rem", display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--accent-teal)" }}>
                        <Activity size={22} /> Savings Plan
                      </h2>
                      <hr style={divider} />
                      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", marginTop: "1.25rem" }}>
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        {result.recommendations.map((rec: any, i: number) => (
                          <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 + i * 0.1 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                              <div style={{ flex: 1 }}>
                                <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.25rem" }}>{rec.action}</h3>
                                <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>{rec.action_detail}</p>
                                <div style={{ fontSize: "0.9rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                                  {([
                                    ["Service", <><strong>{rec.subscription}</strong> (${rec.monthly_cost?.toFixed(2)}/mo)</>],
                                    ["Type", rec.location_type?.replace("_", " ")],
                                    ["Trip", rec.away_reason],
                                    ["Away", rec.away_dates],
                                    ["Duration", `${rec.days_away} days (${rec.months_away} months)`],
                                    ["Savings", <strong style={{ color: "var(--status-safe)" }}>${rec.potential_savings?.toFixed(2)}</strong>],
                                  ] as [string, React.ReactNode][]).map(([label, val]) => (
                                    <p key={label}><span style={{ color: "var(--text-muted)", display: "inline-block", width: "6rem" }}>{label}:</span> {val}</p>
                                  ))}
                                  {rec.penalty > 0 && (<>
                                    <p><span style={{ color: "var(--text-muted)", display: "inline-block", width: "6rem" }}>Rejoin Fee:</span> <span style={{ color: "var(--status-danger)" }}>${rec.penalty?.toFixed(2)}</span></p>
                                    <p><span style={{ color: "var(--text-muted)", display: "inline-block", width: "6rem" }}>Net:</span> <strong style={{ color: "var(--status-safe)" }}>${rec.net_savings?.toFixed(2)}</strong></p>
                                  </>)}
                                  <p><span style={{ color: "var(--text-muted)", display: "inline-block", width: "6rem" }}>Confidence:</span> <span style={{ textTransform: "capitalize" }}>{rec.confidence}</span></p>
                                </div>
                              </div>
                              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", justifyContent: "flex-start" }}>
                                <div style={{ padding: "0.6rem 1.25rem", borderRadius: "980px", fontWeight: 700, fontSize: "1.1rem", color: "#fff", backgroundColor: "var(--status-safe)", boxShadow: "0 2px 8px rgba(52,199,89,0.2)" }}>
                                  Save ${rec.net_savings?.toFixed(2)}
                                </div>
                              </div>
                            </div>

                            {/* Destination Alternatives */}
                            {rec.alternatives && rec.alternatives.alternatives_found && (
                              <div style={{ marginTop: "1rem", borderRadius: "14px", padding: "1.25rem", background: "var(--bg-secondary)" }}>
                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                                  <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>Alternatives in {rec.destination}</span>
                                  <Badge variant="warn" style={{ backgroundColor: "var(--accent-gold)", color: "#fff", fontSize: "0.6rem" }}>SMART TIP</Badge>
                                </div>
                                {rec.alternatives.tip && <p style={{ fontSize: "0.85rem", fontStyle: "italic", color: "var(--text-muted)", marginBottom: "0.75rem" }}>💡 &quot;{rec.alternatives.tip}&quot;</p>}
                                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                                  {rec.alternatives.options?.map((opt: any, j: number) => (
                                    <div key={j} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.85rem", paddingTop: "0.5rem", borderTop: "1px solid var(--border-subtle)" }}>
                                      <div>
                                        {opt.url ? (
                                          <a href={opt.url} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 500, color: "var(--accent-teal)", borderBottom: "1px solid var(--accent-teal-border)" }}>{opt.name} ↗</a>
                                        ) : (<span style={{ fontWeight: 500 }}>{opt.name}</span>)}
                                        <span style={{ color: "var(--text-muted)", marginLeft: "0.5rem" }}>({opt.type})</span>
                                        {opt.notes && <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{opt.notes}</p>}
                                      </div>
                                      <span style={{ fontWeight: 700, color: "var(--accent-gold)" }}>{opt.estimated_cost}</span>
                                    </div>
                                  ))}
                                </div>

                                {/* Cost Comparison */}
                                {(() => {
                                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                                  const cheapest = rec.alternatives.options?.reduce((min: number | null, opt: any) => {
                                    const cost = opt.estimated_monthly_cost;
                                    return (cost && cost > 0 && (min === null || cost < min)) ? cost : min;
                                  }, null as number | null);
                                  if (!cheapest || cheapest <= 0) return null;
                                  const cancelSavings = rec.potential_savings || 0;
                                  const altCost = cheapest * (rec.months_away || 1);
                                  const netImpact = cancelSavings - altCost;
                                  return (
                                    <div style={{ marginTop: "0.75rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border-subtle)", fontSize: "0.9rem" }}>
                                      <p style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", marginBottom: "0.5rem" }}>Cost Comparison ({rec.months_away} months)</p>
                                      <div style={{ display: "flex", justifyContent: "space-between" }}><span>Cancel {rec.subscription}:</span><span style={{ color: "var(--status-safe)" }}>+${cancelSavings.toFixed(2)} saved</span></div>
                                      <div style={{ display: "flex", justifyContent: "space-between" }}><span>{rec.alternatives.best_value_option || "Alternative"} cost:</span><span style={{ color: "var(--status-danger)" }}>-${altCost.toFixed(2)}</span></div>
                                      <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700, marginTop: "0.35rem", paddingTop: "0.35rem", borderTop: "1px solid var(--border-subtle)" }}>
                                        <span>{netImpact >= 0 ? "NET SAVINGS:" : "NET COST:"}</span>
                                        <span style={{ color: netImpact >= 0 ? "var(--status-safe)" : "var(--status-danger)" }}>{netImpact >= 0 ? `$${netImpact.toFixed(2)} ✓` : `-$${Math.abs(netImpact).toFixed(2)}`}</span>
                                      </div>
                                    </div>
                                  );
                                })()}
                              </div>
                            )}

                            {i < result.recommendations.length - 1 && <hr style={{ ...divider, marginTop: "1.5rem" }} />}
                          </motion.div>
                        ))}
                      </div>

                      {/* Total Savings Footer */}
                      <div style={{ textAlign: "center", marginTop: "1.5rem", paddingTop: "1rem", borderTop: "1px solid var(--border-subtle)" }}>
                        <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600, marginBottom: "0.25rem" }}>Total Potential Savings</p>
                        <p style={{ fontSize: "2rem", fontWeight: 700, color: "var(--accent-gold)" }}>${result.total_savings.toFixed(2)}</p>
                      </div>
                    </MotionCard>
                  )}

                  {/* NO-RESULT STATES */}
                  {result.recommendations.length === 0 && result.away_periods.length === 0 && (
                    <MotionCard hover={false} style={{ textAlign: "center", padding: "3rem 2rem" }}>
                      <CheckCircle size={48} style={{ color: "var(--status-safe)", margin: "0 auto 1rem" }} />
                      <h3 style={{ fontSize: "1.15rem", fontWeight: 700, marginBottom: "0.5rem" }}>No Travel Detected</h3>
                      <p style={{ color: "var(--text-muted)" }}>No travel or away periods detected for the next 6 months.</p>
                    </MotionCard>
                  )}
                  {result.recommendations.length === 0 && result.away_periods.length > 0 && (result.local_count || 0) === 0 && (
                    <MotionCard hover={false} style={{ textAlign: "center", padding: "3rem 2rem" }}>
                      <CheckCircle size={48} style={{ color: "var(--status-safe)", margin: "0 auto 1rem" }} />
                      <h3 style={{ fontSize: "1.15rem", fontWeight: 700, marginBottom: "0.5rem" }}>All Subscriptions Are Global</h3>
                      <p style={{ color: "var(--text-muted)" }}>None of your subscriptions are location-dependent. No action needed!</p>
                    </MotionCard>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </main>
    </>
  );
}
