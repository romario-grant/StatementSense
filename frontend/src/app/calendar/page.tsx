"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Calendar as CalendarIcon, MapPin, Plus, Trash2, Plane, Activity, CheckCircle, AlertTriangle, Search, Loader2 } from "lucide-react";
import Navbar from "@/components/Navbar";
import MotionCard from "@/components/MotionCard";
import Badge from "@/components/Badge";

interface SubInput { id: number; name: string; cost: string; }

export default function CalendarSensePage() {
  const [homeLocation, setHomeLocation] = useState("Kingston, Jamaica");
  const [subscriptions, setSubscriptions] = useState<SubInput[]>([{ id: 1, name: "", cost: "" }]);
  const [error, setError] = useState<string | null>(null);

  // Phase 1: Calendar events (fetched on mount)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [events, setEvents] = useState<any[] | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [eventsPreview, setEventsPreview] = useState<any[]>([]);
  const [eventsCount, setEventsCount] = useState(0);
  const [eventsLoading, setEventsLoading] = useState(false);

  // Phase 2: Classification + Travel detection
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [classifyResult, setClassifyResult] = useState<any>(null);
  const [classifyLoading, setClassifyLoading] = useState(false);

  // Phase 3: Savings + Alternatives
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [savingsResult, setSavingsResult] = useState<any>(null);
  const [savingsLoading, setSavingsLoading] = useState(false);

  // Legacy compat: build a combined result object for the existing render code
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result: any = classifyResult ? {
    events_scanned: eventsCount,
    events_preview: eventsPreview,
    away_periods: classifyResult.away_periods || [],
    processed_subscriptions: classifyResult.processed_subscriptions || [],
    local_count: classifyResult.local_count || 0,
    portable_count: classifyResult.portable_count || 0,
    recommendations: savingsResult?.recommendations || [],
    total_savings: savingsResult?.total_savings || 0,
  } : null;

  const phase3Fired = useRef(false);

  // ── Phase 1: Auto-fetch calendar events on mount ──
  useEffect(() => {
    const token = localStorage.getItem("google_access_token") || "";
    if (!token) return;
    setEventsLoading(true);
    fetch("/api/calendar/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: token }),
    })
      .then(async (res) => {
        const text = await res.text();
        let data;
        try {
          data = JSON.parse(text);
        } catch {
          throw new Error(`Server returned invalid response: ${res.status} ${text.slice(0, 50)}`);
        }
        if (!res.ok) {
          throw new Error(data.detail || data.error || `Failed to fetch events: ${res.status}`);
        }
        return data;
      })
      .then(data => {
        if (data.error) { setError(data.error); return; }
        if (!data.events || !Array.isArray(data.events)) {
          throw new Error("Invalid events format received from server");
        }
        setEvents(data.events);
        setEventsPreview(data.events_preview || []);
        setEventsCount(data.events_scanned || 0);
      })
      .catch(err => {
        console.error("Phase 1 Error:", err);
        setError(err.message);
      })
      .finally(() => setEventsLoading(false));
  }, []);

  // ── Phase 3: Auto-fire when Phase 2 reveals local subs + travel ──
  useEffect(() => {
    if (!classifyResult || phase3Fired.current) return;
    const hasLocal = (classifyResult.local_count || 0) > 0;
    const hasTravel = (classifyResult.away_periods || []).length > 0;
    if (hasLocal && hasTravel) {
      phase3Fired.current = true;
      setSavingsLoading(true);
      fetch("/api/calendar/savings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          away_periods: classifyResult.away_periods,
          processed_subscriptions: classifyResult.processed_subscriptions,
        }),
      })
        .then(res => res.json())
        .then(data => { if (!data.error) setSavingsResult(data); })
        .catch(() => {})
        .finally(() => setSavingsLoading(false));
    }
  }, [classifyResult]);

  const handleAddSub = () => setSubscriptions([...subscriptions, { id: Date.now(), name: "", cost: "" }]);
  const handleRemoveSub = (id: number) => setSubscriptions(subscriptions.filter(s => s.id !== id));
  const handleChangeSub = (id: number, field: string, value: string) => setSubscriptions(subscriptions.map(s => s.id === id ? { ...s, [field]: value } : s));

  // ── Phase 2: Classify + Detect (on Analyze click) ──
  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!homeLocation) return setError("Home location is required");
    const validSubs = subscriptions.filter(s => s.name.trim() && s.cost);
    if (validSubs.length === 0) return setError("Please add at least one subscription");
    if (!events || events.length === 0) return setError("Calendar events not loaded yet. Please wait or reconnect.");

    setClassifyLoading(true); setError(null); setClassifyResult(null); setSavingsResult(null); phase3Fired.current = false;
    try {
      const res = await fetch("/api/calendar/classify", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          events,
          home_location: homeLocation,
          subscriptions: validSubs.map(s => ({ name: s.name, cost: parseFloat(s.cost) })),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || data?.error || "Classification failed.");
      setClassifyResult(data);
    } catch (err) { setError(err instanceof Error ? err.message : "An error occurred"); }
    finally { setClassifyLoading(false); }
  };

  return (
    <>
      <Navbar />
      <main className="max-w-6xl mx-auto px-8 pt-32 pb-12">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-8">
          <h1 className="font-light text-4xl md:text-5xl tracking-tighter leading-tight mb-1.5">CalendarSense</h1>
          <p className="text-muted-foreground">Pause local subscriptions while traveling. Connects to your Google Calendar to detect travel periods.</p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* ═══ INPUT COLUMN ═══ */}
          <div className="flex flex-col gap-6">
            <MotionCard hover={false}>
              <h2 className="text-lg font-medium tracking-tight mb-4 flex items-center gap-2">
                Travel Details
              </h2>
              <div>
                <label className="block text-[0.85rem] font-medium mb-1.5">Your Home Location</label>
                <input type="text" className="w-full" value={homeLocation} onChange={e => setHomeLocation(e.target.value)} placeholder="e.g. Kingston, Jamaica" />
                <p className="text-xs text-muted-foreground mt-2">Used to identify which subscriptions are &quot;local&quot; to you.</p>
              </div>
            </MotionCard>

            <MotionCard hover={false} delay={0.05}>
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-medium tracking-tight m-0">Subscriptions</h2>
                <button type="button" onClick={handleAddSub} className="flex items-center gap-1 text-xs px-3 py-1.5 text-foreground bg-primary/10 rounded-full border-none cursor-pointer hover:bg-primary/90 transition-colors">
                  <Plus size={14} /> Add
                </button>
              </div>
              <hr className="border-t border-border my-0" />
              <div className="flex flex-col gap-3 mt-4">
                {subscriptions.map((sub, index) => (
                  <div key={sub.id} className="flex items-center gap-2">
                    <span className="text-muted-foreground text-xs w-4 shrink-0">{index + 1}.</span>
                    <input type="text" placeholder="Name" className="flex-1 min-w-0 text-sm px-3 py-2 rounded-md border bg-transparent focus:outline-none focus:ring-2 focus:ring-ring" value={sub.name} onChange={e => handleChangeSub(sub.id, "name", e.target.value)} />
                    <input type="number" step="0.01" placeholder="$ Cost" className="w-24 min-w-0 text-sm px-3 py-2 rounded-md border bg-transparent focus:outline-none focus:ring-2 focus:ring-ring" value={sub.cost} onChange={e => handleChangeSub(sub.id, "cost", e.target.value)} />
                    <button onClick={() => handleRemoveSub(sub.id)} className="p-2 text-red-500/60 hover:text-red-500 bg-transparent border-none rounded-lg cursor-pointer transition-colors shrink-0"><Trash2 size={15} /></button>
                  </div>
                ))}
                {subscriptions.length === 0 && <p className="text-sm text-muted-foreground text-center py-4">No subscriptions added.</p>}
              </div>
            </MotionCard>

            {error && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="flex gap-2 items-center px-4 py-3 bg-red-500/10 text-red-600 dark:text-red-400 rounded-xl text-[0.85rem]">
                <AlertTriangle size={16} /> <span>{error}</span>
              </motion.div>
            )}

            <MotionCard hover={false} delay={0.1} className="text-center bg-secondary border-border">
              <CalendarIcon size={28} className="text-foreground mx-auto mb-3" />
              <h3 className="font-medium tracking-tight text-base mb-2">
                {eventsLoading ? "Connecting..." : events ? `${eventsCount} Events Loaded` : "Connect & Scan"}
              </h3>
              <p className="text-[0.85rem] text-muted-foreground mb-4">
                {events ? "Enter subscriptions above and analyze for travel overlaps." : "Securely analyze the next 6 months of your Google Calendar."}
              </p>
              <button onClick={handleAnalyze} disabled={classifyLoading || eventsLoading || !events} className="w-full py-3 flex justify-center items-center gap-2 font-medium bg-primary text-primary-foreground rounded-xl disabled:opacity-50 disabled:cursor-not-allowed hover:bg-primary/90 transition-colors shadow-sm">
                {classifyLoading ? (<><Loader2 size={18} className="animate-spin" /> Classifying...</>) : eventsLoading ? (<><Loader2 size={18} className="animate-spin" /> Loading Calendar...</>) : "Analyze Subscriptions"}
              </button>
            </MotionCard>
          </div>

          {/* ═══ RESULTS COLUMN ═══ */}
          <div className="md:col-span-2 relative overflow-hidden rounded-xl min-h-[450px]">
            {/* Persistent Plane Background */}
            <div className="absolute inset-0 bg-cover bg-center pointer-events-none" style={{ backgroundImage: 'url(/PLANE.jpg)' }} />
            <div className="absolute inset-0 bg-black/40 pointer-events-none" />
            
            <div className="relative z-10 h-full">
              <AnimatePresence mode="wait">
                {!result ? (
                  <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full flex flex-col p-4 md:p-6">
                    {/* Header */}
                    <div className="flex items-center justify-between mb-4">
                      <p className="text-sm font-medium text-white/90 tracking-wide uppercase">Your Calendar</p>
                      {eventsLoading && <Loader2 size={16} className="animate-spin text-white/70" />}
                      {events && <span className="text-xs text-white/60">{eventsCount} events</span>}
                    </div>

                    {/* Events List or Empty State */}
                    {eventsLoading ? (
                      <div className="flex flex-col gap-2 flex-1 justify-center">
                        {[1,2,3,4,5].map(i => (
                          <div key={i} className="h-8 rounded-lg bg-white/10 animate-pulse" style={{ animationDelay: `${i * 0.1}s` }} />
                        ))}
                      </div>
                    ) : eventsPreview.length > 0 ? (
                      <div className="flex flex-col gap-1 flex-1 overflow-y-auto pr-1 no-scrollbar pb-6" style={{ maxHeight: '400px' }}>
                        {eventsPreview.map((ev: { date: string; summary: string; location: string }, i: number) => (
                          <motion.div
                            key={i}
                            initial={{ opacity: 0, x: -12 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: 0.1 + i * 0.05 }}
                            className="flex gap-3 text-sm py-2 px-3 rounded-lg bg-black/30 backdrop-blur-md border border-white/10"
                          >
                            <span className="text-white/50 font-mono text-[0.7rem] w-20 shrink-0 pt-0.5">{ev.date}</span>
                            <span className="text-white font-medium truncate">{ev.summary}</span>
                            {ev.location && <span className="text-white/40 text-[0.7rem] ml-auto shrink-0 truncate max-w-[8rem]">{ev.location}</span>}
                          </motion.div>
                        ))}
                        {eventsCount > 15 && <p className="text-xs text-white/40 text-center mt-2">... and {eventsCount - 15} more</p>}
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center flex-1">
                        <motion.div animate={{ y: [0, -8, 0] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
                          <Plane size={48} className="text-white mb-4" />
                        </motion.div>
                        <p className="text-base font-medium tracking-wide uppercase text-white">Ready to Scan</p>
                        <p className="text-[0.85rem] text-white/70 text-center max-w-[18rem] mt-2">
                          {events === null ? "Sign in with Google to load your calendar." : "No upcoming events found."}
                        </p>
                      </div>
                    )}
                  </motion.div>
                ) : (
                  <motion.div key="results" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="h-full flex flex-col p-4 md:p-6 pb-2">
                    
                    {/* Carousel Container */}
                    <div className="flex gap-4 overflow-x-auto snap-x snap-mandatory pb-4 h-full no-scrollbar items-stretch">
                      
                      {/* Slide 1: Summary Stats */}
                      <div className="min-w-[85%] md:min-w-[45%] snap-center shrink-0 flex flex-col h-full justify-center">
                        <div className="grid grid-cols-2 gap-4">
                          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                          {([["Events", result.events_scanned, "text-white"], ["Trips", result.away_periods.length, "text-green-400"], ["Local", result.local_count || 0, "text-yellow-400"], ["Savings", `$${result.total_savings.toFixed(2)}`, "text-yellow-400"]] as [string, any, string][]).map(([label, value, colorClass], i) => (
                            <motion.div key={label} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.06 }} className="text-center py-6 px-3 rounded-xl bg-black/40 backdrop-blur-xl border border-white/10">
                              <p className="text-[0.7rem] text-white/70 uppercase tracking-[0.06em] font-medium mb-1.5">{label}</p>
                              <p className={`text-3xl font-medium ${colorClass}`}>{value}</p>
                            </motion.div>
                          ))}
                        </div>
                        <p className="text-white/40 text-xs text-center mt-6 animate-pulse">Swipe to see details →</p>
                      </div>

                      {/* Slide 2: Travel Detection */}
                      <div className="min-w-[90%] md:min-w-[65%] snap-center shrink-0 h-full">
                        <div className="h-[400px] rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col overflow-hidden">
                          <div className="p-5 border-b border-white/10">
                            <h3 className="font-medium flex items-center gap-2 m-0 text-white"><Plane size={18} className="text-white/70" /> Travel Detection</h3>
                          </div>
                          <div className="flex-1 overflow-y-auto p-5 no-scrollbar">
                            {result.away_periods.length === 0 ? (
                              <div className="text-center py-8"><p className="text-white/50">No travel detected in the next 6 months.</p></div>
                            ) : (
                              <div className="flex flex-col gap-4">
                                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                                {result.away_periods.map((away: any, i: number) => {
                                  const days = Math.ceil((new Date(away.return_date).getTime() - new Date(away.departure_date).getTime()) / (1000 * 60 * 60 * 24));
                                  return (
                                    <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 + i * 0.08 }} className="p-4 rounded-xl bg-white/5 border border-white/5 text-white">
                                      <div className="flex justify-between items-start mb-2">
                                        <p className="font-medium flex items-center gap-2 text-sm">
                                          <span>{away.confidence === "high" ? "🟢" : away.confidence === "medium" ? "🟡" : "🔴"}</span> {away.reason}
                                        </p>
                                        <Badge variant={away.confidence === "high" ? "safe" : "warn"} className="capitalize text-[0.65rem] border-white/10">{away.confidence} confidence</Badge>
                                      </div>
                                      <div className="grid grid-cols-3 gap-4 text-[0.8rem] mt-3">
                                        <div><span className="text-[0.65rem] text-white/50 block">Dates</span><span className="font-medium">{away.departure_date} → {away.return_date}</span></div>
                                        <div><span className="text-[0.65rem] text-white/50 block">Destination</span><span className="font-medium truncate max-w-[8rem]">{away.destination || "Unknown"}</span></div>
                                        <div><span className="text-[0.65rem] text-white/50 block">Duration</span><span className="font-medium">{days} days</span></div>
                                      </div>
                                      {away.trigger_type && <div className="mt-3"><span className="text-[0.65rem] px-2 py-1 rounded-full bg-white/10 capitalize">{away.trigger_type}</span></div>}
                                    </motion.div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Slide 3: Subscription Classification */}
                      <div className="min-w-[90%] md:min-w-[65%] snap-center shrink-0 h-full">
                        <div className="h-[400px] rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col overflow-hidden">
                          <div className="p-5 border-b border-white/10">
                            <h3 className="font-medium flex items-center gap-2 m-0 text-white"><Search size={18} className="text-white/70" /> Subscription Classification</h3>
                          </div>
                          <div className="flex-1 overflow-y-auto p-5 no-scrollbar">
                            <div className="flex flex-col gap-3">
                              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                              {result.processed_subscriptions.map((sub: any, i: number) => (
                                <motion.div key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 + i * 0.07 }} className={`p-4 rounded-xl border ${sub.is_local ? "bg-yellow-500/10 border-yellow-500/30" : "bg-white/5 border-white/5"} text-white`}>
                                  <div className="flex justify-between items-center mb-2">
                                    <span className="font-medium text-base">{sub.name}</span>
                                    <Badge variant={sub.is_local ? "danger" : "safe"} className="font-medium text-[0.65rem]">{sub.is_local ? "LOCAL" : "GLOBAL"}</Badge>
                                  </div>
                                  <p className="text-[0.8rem] text-white/60 mb-3">{sub.reason}</p>
                                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[0.8rem]">
                                    <div className="flex justify-between pb-1 border-b border-white/10">
                                      <span className="text-[0.7rem] text-white/50">Type</span>
                                      <span className="font-medium capitalize">{sub.location_type?.replace("_", " ")}</span>
                                    </div>
                                    <div className="flex justify-between pb-1 border-b border-white/10">
                                      <span className="text-[0.7rem] text-white/50">Cost</span>
                                      <span className="font-medium">${(sub.monthly_cost || 0).toFixed(2)}/mo</span>
                                    </div>
                                    {sub.is_local && (
                                      <div className="flex justify-between pb-1 border-b border-white/10 col-span-2 mt-1">
                                        <span className="text-[0.7rem] text-white/50">Can Cancel</span>
                                        <span className="font-medium">{sub.can_cancel_and_rejoin ? "✓ Yes" : "✗ No"}</span>
                                      </div>
                                    )}
                                    {sub.cancellation_penalty > 0 && sub.is_local && (
                                      <div className="flex justify-between pb-1 border-b border-white/10 col-span-2">
                                        <span className="text-[0.7rem] text-white/50">Penalty</span>
                                        <span className="font-medium text-red-400">${sub.cancellation_penalty}</span>
                                      </div>
                                    )}
                                  </div>
                                </motion.div>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Slide 4: Savings Plan */}
                      {result.recommendations.length > 0 && (
                        <div className="min-w-[95%] md:min-w-[75%] snap-center shrink-0 h-full">
                          <div className="h-[400px] rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col overflow-hidden">
                            <div className="p-5 border-b border-white/10 flex justify-between items-center">
                              <h3 className="font-medium flex items-center gap-2 m-0 text-white"><Activity size={18} className="text-white/70" /> Savings Plan</h3>
                              <span className="font-bold text-yellow-400 text-lg">${result.total_savings.toFixed(2)}</span>
                            </div>
                            <div className="flex-1 overflow-y-auto p-5 no-scrollbar">
                              <div className="flex flex-col gap-6">
                                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                                {result.recommendations.map((rec: any, i: number) => (
                                  <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 + i * 0.1 }} className="text-white">
                                    <div className="flex justify-between gap-4 flex-wrap mb-4">
                                      <div className="flex-1">
                                        <h3 className="text-base font-medium mb-1 text-white">{rec.action}</h3>
                                        <p className="text-[0.8rem] text-white/70 mb-3">{rec.action_detail}</p>
                                        <div className="grid grid-cols-2 gap-y-2 text-[0.8rem] bg-white/5 p-3 rounded-lg border border-white/5">
                                          <p><span className="text-white/50 block text-[0.65rem]">Service</span> <strong>{rec.subscription}</strong></p>
                                          <p><span className="text-white/50 block text-[0.65rem]">Duration</span> {rec.days_away} days</p>
                                          <p><span className="text-white/50 block text-[0.65rem]">Trip</span> <span className="truncate block max-w-[8rem]">{rec.away_reason}</span></p>
                                          <p><span className="text-white/50 block text-[0.65rem]">Net Savings</span> <strong className="text-green-400">${rec.net_savings?.toFixed(2)}</strong></p>
                                        </div>
                                      </div>
                                    </div>

                                    {/* Destination Alternatives */}
                                    {rec.alternatives && rec.alternatives.alternatives_found && (
                                      <div className="rounded-xl p-4 bg-yellow-500/10 border border-yellow-500/20">
                                        <div className="flex items-center justify-between mb-2">
                                          <span className="font-medium text-[0.8rem] text-yellow-100">Alternatives in {rec.destination}</span>
                                          <Badge variant="warn" className="bg-yellow-500 text-black text-[0.6rem] border-none">TIP</Badge>
                                        </div>
                                        {rec.alternatives.tip && <p className="text-[0.75rem] italic text-white/60 mb-3">&quot;{rec.alternatives.tip}&quot;</p>}
                                        
                                        {/* Cost Comparison */}
                                        {(() => {
                                          // eslint-disable-next-line @typescript-eslint/no-explicit-any
                                          const cheapest = rec.alternatives.options?.reduce((min: number | null, opt: any) => {
                                            const cost = opt.estimated_monthly_cost;
                                            return (cost && cost > 0 && (min === null || cost < min)) ? cost : min;
                                          }, null as number | null);
                                          if (!cheapest || cheapest <= 0) return null;
                                          const altCost = cheapest * (rec.months_away || 1);
                                          return (
                                            <div className="mt-2 text-[0.85rem] bg-black/20 p-3 rounded-lg">
                                              <p className="text-center font-medium">Potential savings if you subscribe to alternative:</p>
                                              <p className="text-center text-xl font-bold text-green-400 mt-1">${(rec.potential_savings - altCost).toFixed(2)}</p>
                                            </div>
                                          );
                                        })()}

                                        <div className="flex flex-col gap-2 mt-3">
                                          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                                          {rec.alternatives.options?.map((opt: any, j: number) => (
                                            <div key={j} className="flex justify-between items-center text-[0.8rem] pt-2 border-t border-white/10">
                                              <div>
                                                {opt.url ? (
                                                  <a href={opt.url} target="_blank" rel="noopener noreferrer" className="font-medium text-white hover:text-yellow-400 transition-colors">{opt.name} ↗</a>
                                                ) : (<span className="font-medium text-white">{opt.name}</span>)}
                                                <span className="text-white/50 ml-2">({opt.type})</span>
                                              </div>
                                              <span className="font-medium text-yellow-400">{opt.estimated_cost}</span>
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                    {i < result.recommendations.length - 1 && <hr className="border-t border-white/10 my-6" />}
                                  </motion.div>
                                ))}
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* SAVINGS LOADING SKELETON */}
                      {savingsLoading && (
                        <div className="min-w-[95%] md:min-w-[75%] snap-center shrink-0 h-full">
                          <div className="h-[400px] rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col p-6 justify-center items-center text-white">
                            <Loader2 size={32} className="animate-spin text-white mb-4" />
                            <h2 className="text-lg font-medium">Calculating Savings...</h2>
                            <p className="text-white/50 text-sm mt-2 text-center max-w-xs">Analyzing local alternative gym and service prices in your travel destinations.</p>
                          </div>
                        </div>
                      )}

                      {/* NO-RESULT STATES */}
                      {result.recommendations.length === 0 && !savingsLoading && result.away_periods.length === 0 && (
                        <div className="min-w-[95%] md:min-w-[75%] snap-center shrink-0 h-full">
                          <div className="h-[400px] rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col p-6 justify-center items-center text-white">
                            <CheckCircle size={48} className="text-green-400 mb-4" />
                            <h3 className="text-xl font-medium mb-2">No Travel Detected</h3>
                            <p className="text-white/60 text-center">No travel or away periods detected for the next 6 months.</p>
                          </div>
                        </div>
                      )}
                      {result.recommendations.length === 0 && !savingsLoading && result.away_periods.length > 0 && (result.local_count || 0) === 0 && (
                        <div className="min-w-[95%] md:min-w-[75%] snap-center shrink-0 h-full">
                          <div className="h-[400px] rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col p-6 justify-center items-center text-white">
                            <CheckCircle size={48} className="text-green-400 mb-4" />
                            <h3 className="text-xl font-medium mb-2">All Subscriptions Global</h3>
                            <p className="text-white/60 text-center">None of your subscriptions are location-dependent. No action needed!</p>
                          </div>
                        </div>
                      )}

                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
