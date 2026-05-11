"use client";

import { useState, useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import { Calendar as CalendarIcon, MapPin, Plus, Trash2, Plane, Activity, CheckCircle, AlertTriangle, Search, Loader2, CalendarPlus, Clock, Info } from "lucide-react";
import Navbar from "@/components/Navbar";
import MotionCard from "@/components/MotionCard";
import Badge from "@/components/Badge";
import {
  readSharedSubscriptions,
  sharedSubscriptionsSignature,
} from "@/lib/subscriptionStore";
import { readPageSession, savePageSession } from "@/lib/pageSessionStore";

// Lazy-load map component (requires browser APIs)
const PlacesMap = dynamic(() => import("./PlacesMap"), { ssr: false });

interface SubInput { id: number; name: string; cost: string; renewalDay: string; }

type CalendarSession = {
  sourceSignature?: string;
  homeLocation: string;
  subscriptions: SubInput[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  events: any[] | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  eventsPreview: any[];
  eventsCount: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  classifyResult: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  savingsResult: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  remindersResult: any;
};

export default function CalendarSensePage() {
  const [homeLocation, setHomeLocation] = useState("Kingston, Jamaica");
  const [subscriptions, setSubscriptions] = useState<SubInput[]>([]);
  const [showAddSubscription, setShowAddSubscription] = useState(false);
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

  // Phase 3: Savings + Alternatives (Places API)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [savingsResult, setSavingsResult] = useState<any>(null);
  const [savingsLoading, setSavingsLoading] = useState(false);

  // Phase 4: Calendar reminders
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [remindersResult, setRemindersResult] = useState<any>(null);
  const [remindersLoading, setRemindersLoading] = useState(false);

  // Legacy compat: build a combined result object for the render code
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
  const [sourceSignature, setSourceSignature] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const detected = readSharedSubscriptions();
    const nextSourceSignature = sharedSubscriptionsSignature(detected);
    const saved = readPageSession<CalendarSession>("calendar");
    if (saved?.sourceSignature === nextSourceSignature) {
      // Restore the in-progress CalendarSense workflow when returning to the page.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setHomeLocation(saved.homeLocation);
      setSubscriptions(saved.subscriptions);
      setEvents(saved.events);
      setEventsPreview(saved.eventsPreview);
      setEventsCount(saved.eventsCount);
      setClassifyResult(saved.classifyResult);
      setSavingsResult(saved.savingsResult);
      setRemindersResult(saved.remindersResult);
      phase3Fired.current = Boolean(saved.savingsResult);
    } else {
      if (saved?.homeLocation) setHomeLocation(saved.homeLocation);
      if (saved?.events) setEvents(saved.events);
      if (saved?.eventsPreview) setEventsPreview(saved.eventsPreview);
      if (saved?.eventsCount) setEventsCount(saved.eventsCount);
      phase3Fired.current = false;
      if (detected.length > 0) {
        setSubscriptions(
          detected.map((sub, index) => ({
            id: sub.id || Date.now() + index,
            name: sub.name,
            cost: sub.cost.toString(),
            renewalDay: sub.renewalDay ? String(sub.renewalDay) : "",
          }))
        );
      }
    }
    setSourceSignature(nextSourceSignature);
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated || subscriptions.length > 0) return;
    const detected = readSharedSubscriptions();
    if (detected.length === 0) return;
    // Load the browser handoff once when CalendarSense opens.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSubscriptions(
      detected.map((sub, index) => ({
        id: sub.id || Date.now() + index,
        name: sub.name,
        cost: sub.cost.toString(),
        renewalDay: sub.renewalDay ? String(sub.renewalDay) : "",
      }))
    );
  }, [hydrated, subscriptions.length]);

  useEffect(() => {
    if (!hydrated) return;
    savePageSession("calendar", {
      sourceSignature,
      homeLocation,
      subscriptions,
      events,
      eventsPreview,
      eventsCount,
      classifyResult,
      savingsResult,
      remindersResult,
    });
  }, [
    classifyResult,
    events,
    eventsCount,
    eventsPreview,
    homeLocation,
    hydrated,
    remindersResult,
    savingsResult,
    sourceSignature,
    subscriptions,
  ]);

  // ── Phase 1: Auto-fetch calendar events on mount ──
  useEffect(() => {
    if (!hydrated || events) return;
    const token = localStorage.getItem("google_access_token") || "";
    if (!token) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
  }, [events, hydrated]);

  // ── Phase 3: Auto-fire when Phase 2 reveals local subs + travel ──
  useEffect(() => {
    if (!classifyResult || phase3Fired.current) return;
    const hasLocal = (classifyResult.local_count || 0) > 0;
    const hasTravel = (classifyResult.away_periods || []).length > 0;
    if (hasLocal && hasTravel) {
      phase3Fired.current = true;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSavingsLoading(true);
      fetch("/api/calendar/savings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          away_periods: classifyResult.away_periods,
          processed_subscriptions: classifyResult.processed_subscriptions,
        }),
      })
        .then(async (res) => {
          const data = await res.json();
          if (!res.ok || data.error) {
            throw new Error(data.detail || data.error || "Could not calculate travel alternatives.");
          }
          return data;
        })
        .then(setSavingsResult)
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Could not calculate travel alternatives.");
        })
        .finally(() => setSavingsLoading(false));
    }
  }, [classifyResult]);

  const handleAddSub = () => {
    setShowAddSubscription(true);
    setSubscriptions([...subscriptions, { id: Date.now(), name: "", cost: "", renewalDay: "" }]);
  };
  const handleRemoveSub = (id: number) => setSubscriptions(subscriptions.filter(s => s.id !== id));
  const handleChangeSub = (id: number, field: string, value: string) => setSubscriptions(subscriptions.map(s => s.id === id ? { ...s, [field]: value } : s));

  // ── Phase 2: Classify + Detect (on Analyze click) ──
  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!homeLocation) return setError("Home location is required");
    const validSubs = subscriptions.filter(s => s.name.trim() && s.cost);
    if (validSubs.length === 0) return setError("Please add at least one subscription");
    if (!events || events.length === 0) return setError("Calendar events not loaded yet. Please wait or reconnect.");

    setClassifyLoading(true); setError(null); setClassifyResult(null); setSavingsResult(null); setRemindersResult(null); phase3Fired.current = false;
    try {
      const res = await fetch("/api/calendar/classify", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          events,
          home_location: homeLocation,
          subscriptions: validSubs.map(s => ({
            name: s.name,
            cost: parseFloat(s.cost),
            renewal_day: s.renewalDay ? parseInt(s.renewalDay) : null,
          })),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || data?.error || "Classification failed.");
      setClassifyResult(data);
    } catch (err) { setError(err instanceof Error ? err.message : "An error occurred"); }
    finally { setClassifyLoading(false); }
  };

  // ── Phase 4: Add reminders to calendar ──
  const handleAddReminders = async () => {
    if (!savingsResult?.recommendations?.length) return;
    const token = localStorage.getItem("google_access_token");
    if (!token) { setError("Google access token not found. Please re-login."); return; }

    setRemindersLoading(true);
    try {
      const res = await fetch("/api/calendar/reminders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          access_token: token,
          recommendations: savingsResult.recommendations.filter(
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (r: any) => r.action !== "KEEP"
          ),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || data?.error || "Failed to create reminders.");
      setRemindersResult(data);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create reminders"); }
    finally { setRemindersLoading(false); }
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
                  <Plus size={14} /> {subscriptions.length ? "Add another" : "Add subscription"}
                </button>
              </div>
              <hr className="border-t border-border my-0" />
              {subscriptions.length > 0 && (
                <p className="text-xs text-muted-foreground mt-3 mb-0">
                  Detected subscriptions are prefilled from SubscriptionSense. Add another if anything is missing.
                </p>
              )}
              <div className="flex flex-col gap-3 mt-4">
                {subscriptions.map((sub, index) => (
                  <div key={sub.id} className="flex flex-col gap-2 p-3 rounded-xl border bg-background/30 shadow-sm">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 flex-1">
                        <span className="text-muted-foreground text-xs w-4 shrink-0 font-medium">{index + 1}.</span>
                        <input type="text" placeholder="Subscription Name" className="flex-1 min-w-0 text-sm px-3 py-2 rounded-md border bg-transparent focus:outline-none focus:ring-2 focus:ring-ring" value={sub.name} onChange={e => handleChangeSub(sub.id, "name", e.target.value)} />
                      </div>
                      <button onClick={() => handleRemoveSub(sub.id)} className="p-2 text-red-500/60 hover:text-red-500 bg-transparent border-none rounded-lg cursor-pointer transition-colors shrink-0"><Trash2 size={15} /></button>
                    </div>
                    <div className="flex items-center gap-2 pl-8">
                      <div className="relative flex-1">
                        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">$</span>
                        <input type="number" step="0.01" placeholder="Cost/mo" className="w-full text-sm pl-7 pr-3 py-2 rounded-md border bg-transparent focus:outline-none focus:ring-2 focus:ring-ring" value={sub.cost} onChange={e => handleChangeSub(sub.id, "cost", e.target.value)} />
                      </div>
                      <input type="number" min="1" max="31" placeholder="Renewal Day (1-31)" className="flex-1 min-w-0 text-sm px-3 py-2 rounded-md border bg-transparent focus:outline-none focus:ring-2 focus:ring-ring" value={sub.renewalDay} onChange={e => handleChangeSub(sub.id, "renewalDay", e.target.value)} />
                    </div>
                  </div>
                ))}
                {subscriptions.length === 0 && !showAddSubscription && <p className="text-sm text-muted-foreground text-center py-4">Run SubscriptionSense first, or add a subscription manually.</p>}
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
            
            <div className="absolute inset-0 z-10">
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
                      <div className="flex flex-col gap-1 flex-1 overflow-y-auto pr-1 no-scrollbar pb-6" style={{ maskImage: 'linear-gradient(to bottom, black 0%, black 95%, transparent)', WebkitMaskImage: 'linear-gradient(to bottom, black 0%, black 95%, transparent)' }}>
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
                    
                    {/* Vertical Scroll Container */}
                    <div className="flex flex-col gap-6 overflow-y-auto pb-8 h-full pr-2 no-scrollbar pt-2" style={{ maskImage: 'linear-gradient(to bottom, black 0%, black 95%, transparent)', WebkitMaskImage: 'linear-gradient(to bottom, black 0%, black 95%, transparent)' }}>
                      
                      {/* Slide 1: Summary Stats */}
                      <div className="flex flex-col gap-2">
                        <div className="grid grid-cols-4 gap-2 md:gap-4">
                          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                          {([["Events", result.events_scanned, "text-white"], ["Trips", result.away_periods.length, "text-green-400"], ["Local", result.local_count || 0, "text-yellow-400"], ["Savings", `$${result.total_savings.toFixed(2)}`, "text-yellow-400"]] as [string, any, string][]).map(([label, value, colorClass], i) => (
                            <motion.div key={label} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.06 }} className="text-center py-3 px-2 rounded-xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col justify-center min-h-[80px]">
                              <p className="text-[0.6rem] md:text-[0.65rem] text-white/70 uppercase tracking-[0.06em] font-medium mb-1">{label}</p>
                              <p className={`text-xl md:text-2xl font-medium ${colorClass}`}>{value}</p>
                            </motion.div>
                          ))}
                        </div>
                      </div>

                      {/* Slide 2: Travel Detection */}
                      <div>
                        <div className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col overflow-hidden">
                          <div className="p-5 border-b border-white/10">
                            <h3 className="font-medium flex items-center gap-2 m-0 text-white"><Plane size={18} className="text-white/70" /> Travel Detection</h3>
                          </div>
                          <div className="p-5">
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
                      <div>
                        <div className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col overflow-hidden">
                          <div className="p-5 border-b border-white/10">
                            <h3 className="font-medium flex items-center gap-2 m-0 text-white"><Search size={18} className="text-white/70" /> Subscription Classification</h3>
                          </div>
                          <div className="p-5">
                            <div className="flex flex-col gap-3">
                              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                              {result.processed_subscriptions.map((sub: any, i: number) => (
                                <motion.div key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 + i * 0.07 }} className={`p-4 rounded-xl border ${sub.is_local ? "bg-yellow-500/10 border-yellow-500/30" : "bg-white/5 border-white/5"} text-white`}>
                                  <div className="flex justify-between items-center mb-2">
                                    <span className="font-medium text-base">{sub.name}</span>
                                    <Badge variant={sub.is_local ? "danger" : "safe"} className="font-medium text-[0.65rem]">{sub.is_local ? "LOCAL" : "GLOBAL"}</Badge>
                                  </div>
                                  <div className="grid grid-cols-1 gap-y-1.5 text-[0.8rem]">
                                    <div className="flex justify-between pb-1 border-b border-white/10">
                                      <span className="text-[0.7rem] text-white/50">Cost</span>
                                      <span className="font-medium">${(sub.monthly_cost || 0).toFixed(2)}/mo</span>
                                    </div>
                                    {sub.is_local && (
                                      <div className="flex justify-between pb-1 border-b border-white/10 mt-1">
                                        <span className="text-[0.7rem] text-white/50">Can Cancel</span>
                                        <span className="font-medium">{sub.can_cancel_and_rejoin ? "✓ Yes" : "✗ No"}</span>
                                      </div>
                                    )}
                                    {sub.cancellation_penalty > 0 && sub.is_local && (
                                      <div className="flex justify-between pb-1 border-b border-white/10">
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

                      {/* Slide 4: Smart Recommendations & Map */}
                      {result.recommendations.length > 0 && (
                        <div>
                          <div className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col overflow-hidden">
                            <div className="p-5 border-b border-white/10 flex justify-between items-center">
                              <h3 className="font-medium flex items-center gap-2 m-0 text-white"><Activity size={18} className="text-white/70" /> Smart Recommendations</h3>
                              <span className="font-bold text-yellow-400 text-lg">${result.total_savings.toFixed(2)} savings</span>
                            </div>
                            <div className="p-5">
                              <div className="flex flex-col gap-8">
                                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                                {result.recommendations.map((rec: any, i: number) => (
                                  <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 + i * 0.1 }} className="text-white">
                                    <div className="flex justify-between gap-4 flex-wrap mb-4">
                                      <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-2">
                                          <h3 className="text-base font-semibold m-0">{rec.action} {rec.subscription}</h3>
                                          <Badge variant={rec.action === "KEEP" ? "info" : "safe"} className="text-[0.65rem]">{rec.net_savings > 0 ? `$${rec.net_savings.toFixed(2)} saved` : "Advisory"}</Badge>
                                        </div>
                                        <p className="text-[0.85rem] text-white/80 mb-2">{rec.action_detail}</p>
                                        <p className="text-[0.75rem] text-white/50 italic mb-4">&ldquo;{rec.rationale}&rdquo;</p>
                                        
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[0.8rem] bg-white/5 p-4 rounded-xl border border-white/5">
                                          <div className="flex flex-col gap-1">
                                            <span className="text-white/50 text-[0.65rem] uppercase tracking-wider flex items-center gap-1"><Clock size={12} /> Timing</span>
                                            <span className="font-medium">{rec.timing_context || "Unknown"}</span>
                                          </div>
                                          <div className="flex flex-col gap-1">
                                            <span className="text-white/50 text-[0.65rem] uppercase tracking-wider flex items-center gap-1"><Plane size={12} /> Trip</span>
                                            <span className="font-medium truncate" title={rec.away_reason}>{rec.away_reason}</span>
                                          </div>
                                          <div className="flex flex-col gap-1">
                                            <span className="text-white/50 text-[0.65rem] uppercase tracking-wider flex items-center gap-1"><MapPin size={12} /> Destination</span>
                                            <span className="font-medium truncate" title={rec.destination}>{rec.destination}</span>
                                          </div>
                                          <div className="flex flex-col gap-1">
                                            <span className="text-white/50 text-[0.65rem] uppercase tracking-wider flex items-center gap-1"><Activity size={12} /> Duration</span>
                                            <span className="font-medium">{rec.days_away} days</span>
                                          </div>
                                        </div>
                                      </div>
                                    </div>

                                    {/* Destination Map Integration */}
                                    {rec.alternatives && rec.alternatives.alternatives_found && (
                                      <div className="mt-6 mb-2">
                                        <PlacesMap
                                          center={rec.alternatives.destination_center}
                                          markers={rec.alternatives.options}
                                          destination={rec.destination}
                                          subscriptionName={rec.subscription}
                                        />
                                        {rec.alternatives.cost_comparison && (
                                          <div className="mt-3 rounded-xl border border-white/10 bg-[#05080c] p-4 text-sm text-white">
                                            <div className="flex flex-wrap items-start justify-between gap-3">
                                              <div>
                                                <p className="text-xs uppercase tracking-wider text-white/45">Alternative Cost Outlook</p>
                                                <p className="mt-1 font-medium">
                                                  Cheapest likely option: {rec.alternatives.cost_comparison.cheapest_option_name}
                                                </p>
                                                <p className="text-white/55">
                                                  Estimated cost: {rec.alternatives.cost_comparison.estimated_cost}
                                                </p>
                                              </div>
                                              <div className="text-left md:text-right">
                                                <p className="text-xs uppercase tracking-wider text-white/45">Compared With Current Plan</p>
                                                <p className={`mt-1 font-semibold ${rec.alternatives.cost_comparison.comparison_to_subscription <= 0 ? "text-green-400" : "text-yellow-400"}`}>
                                                  {rec.alternatives.cost_comparison.comparison_to_subscription <= 0 ? "About " : "About +"}
                                                  ${Math.abs(rec.alternatives.cost_comparison.comparison_to_subscription).toFixed(2)}
                                                  {rec.alternatives.cost_comparison.comparison_to_subscription <= 0 ? " less" : " more"} per month
                                                </p>
                                              </div>
                                            </div>
                                            {rec.alternatives.cost_comparison.explanation && (
                                              <p className="mt-3 text-xs leading-relaxed text-white/55">
                                                {rec.alternatives.cost_comparison.explanation}
                                              </p>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    )}

                                    {i < result.recommendations.length - 1 && <hr className="border-t border-white/10 my-8" />}
                                  </motion.div>
                                ))}

                                {/* Add to Calendar Button */}
                                {result.recommendations.some((r: { action?: string }) => r.action !== "KEEP") && (
                                  <div className="mt-4 pt-6 border-t border-white/10 flex flex-col items-center">
                                    {remindersResult ? (
                                      <div className="bg-green-500/10 border border-green-500/20 text-green-400 p-4 rounded-xl text-sm flex flex-col gap-2 w-full">
                                        <div className="flex items-center gap-2 font-medium">
                                          <CheckCircle size={16} /> Successfully created {remindersResult.total_created} calendar reminders!
                                        </div>
                                        <div className="flex flex-col gap-1 mt-1">
                                          {remindersResult.created_events?.map((ev: { event_link: string; date: string; summary: string }, idx: number) => (
                                            <a key={idx} href={ev.event_link} target="_blank" rel="noopener noreferrer" className="text-xs text-green-400/80 hover:text-green-300 flex items-center gap-1">
                                              <span>{ev.date}: {ev.summary}</span>
                                            </a>
                                          ))}
                                        </div>
                                      </div>
                                    ) : (
                                      <>
                                        <button
                                          onClick={handleAddReminders}
                                          disabled={remindersLoading}
                                          className="flex items-center gap-2 px-6 py-3 bg-white text-black font-medium rounded-full hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                          {remindersLoading ? <Loader2 size={18} className="animate-spin" /> : <CalendarPlus size={18} />}
                                          {remindersLoading ? "Creating calendar events..." : "Add Dates to Google Calendar"}
                                        </button>
                                        <p className="text-xs text-white/50 mt-3 text-center">
                                          Adds calendar events for the recommended pause or cancel date,<br />
                                          plus a restart date for when you return.
                                        </p>
                                      </>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* SAVINGS LOADING SKELETON */}
                      {savingsLoading && (
                        <div>
                          <div className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col p-6 justify-center items-center text-white min-h-[300px]">
                            <Loader2 size={32} className="animate-spin text-white mb-4" />
                            <h2 className="text-lg font-medium">Calculating Savings...</h2>
                            <p className="text-white/50 text-sm mt-2 text-center max-w-xs">Analyzing local alternative gym and service prices in your travel destinations.</p>
                          </div>
                        </div>
                      )}

                      {/* NO-RESULT STATES */}
                      {result.recommendations.length === 0 && !savingsLoading && result.away_periods.length === 0 && (
                        <div>
                          <div className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col p-6 justify-center items-center text-white min-h-[300px]">
                            <CheckCircle size={48} className="text-green-400 mb-4" />
                            <h3 className="text-xl font-medium mb-2">No Travel Detected</h3>
                            <p className="text-white/60 text-center">No travel or away periods detected for the next 6 months.</p>
                          </div>
                        </div>
                      )}
                      {result.recommendations.length === 0 && !savingsLoading && result.away_periods.length > 0 && (result.local_count || 0) === 0 && (
                        <div>
                          <div className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col p-6 justify-center items-center text-white min-h-[300px]">
                            <CheckCircle size={48} className="text-green-400 mb-4" />
                            <h3 className="text-xl font-medium mb-2">All Subscriptions Global</h3>
                            <p className="text-white/60 text-center">None of your subscriptions are location-dependent. No action needed!</p>
                          </div>
                        </div>
                      )}
                      {result.recommendations.length === 0 && !savingsLoading && result.away_periods.length > 0 && (result.local_count || 0) > 0 && (
                        <div>
                          <div className="rounded-2xl bg-black/40 backdrop-blur-xl border border-white/10 flex flex-col p-6 justify-center items-center text-white min-h-[300px]">
                            <Info size={48} className="text-yellow-400 mb-4" />
                            <h3 className="text-xl font-medium mb-2">No Travel Action Needed</h3>
                            <p className="text-white/60 text-center">
                              Your local subscription was detected, but CalendarSense did not find a useful pause or cancel action for this trip.
                            </p>
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
