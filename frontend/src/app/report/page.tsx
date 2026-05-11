"use client";

import { useEffect, useMemo, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
  Download,
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  Info,
  Plane,
  RefreshCw,
  Sparkles,
  XCircle,
  ArrowRight,
  GraduationCap,
  Tv,
  Calendar,
  DollarSign,
  ShieldAlert,
} from "lucide-react";
import Navbar from "@/components/Navbar";
import MotionCard from "@/components/MotionCard";
import Badge from "@/components/Badge";
import {
  readSharedSubscriptions,
  readSubscriptionAnalysis,
  sharedSubscriptionsSignature,
  subscriptionAnalysisSignature,
} from "@/lib/subscriptionStore";
import { readPageSession } from "@/lib/pageSessionStore";
import { readUserPreferences } from "@/lib/userPreferenceStore";

// ─── Types (mirrors existing codebase shapes) ────────────────────────────────

type SubscriptionResult = {
  merchant: string;
  amount: number;
  period: string;
  period_days: number | null;
  confidence: number;
  confidence_label?: string;
  charge_count: number;
  renewal_day?: number;
  last_charge: string;
  source?: "subscription-sense" | "manual";
};

type RenewalPrediction = {
  subscription: string;
  next_charge_date: string;
  days_until_charge: number;
  period: string;
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
  old_amount: number;
  new_amount: number;
  change_amount: number;
  change_percent: number;
  description: string;
};

type SubscriptionAnalysis = {
  bank_detected: string;
  transactions_parsed: number;
  currency: string;
  summary: {
    total_subscriptions: number;
    total_sub_cost: number;
    total_trial_alerts: number;
    total_price_changes: number;
  };
  currency_summary?: {
    exchange_rate: number;
    original_currency: string;
    subscription_spend_local?: number;
    subscription_spend_usd?: number;
  };
  subscriptions: SubscriptionResult[];
  renewal_predictions?: RenewalPrediction[];
  trial_alerts?: TrialAlert[];
  price_changes?: PriceChange[];
};

type RenewalSub = {
  subscription: string;
  amount: number;
  renewal_day: number;
  risk_level: "low" | "moderate" | "high";
  risk_label: string;
  risk_score: number;
  advice: string;
  fail_history: number;
  breakdown: {
    days_since_payday: number;
    subscription_load_factor: number;
    nearby_spend: number;
    spend_before_factor: number;
  };
};

type CalendarRec = {
  subscription: string;
  action: string;
  action_detail: string;
  rationale: string;
  net_savings: number;
  destination: string;
  days_away: number;
  away_reason: string;
};

// ─── Intelligence helpers ────────────────────────────────────────────────────

const STREAMING_NAMES = new Set([
  "netflix", "disney+", "hulu", "hbo max", "max", "amazon prime",
  "apple tv", "peacock", "paramount+", "crunchyroll", "espn+",
  "discovery+", "showtime", "starz", "mubi", "shudder", "tidal",
]);

const STUDENT_ELIGIBLE: Record<string, { discount: number; planName: string }> = {
  spotify: { discount: 50, planName: "Spotify Premium Student (~$2.99/mo)" },
  apple: { discount: 50, planName: "Apple One Student" },
  youtube: { discount: 45, planName: "YouTube Premium Student" },
  hulu: { discount: 80, planName: "Hulu Student (special pricing)" },
  microsoft: { discount: 0, planName: "Microsoft 365 Education (free)" },
  office: { discount: 0, planName: "Microsoft 365 Education (free)" },
  adobe: { discount: 60, planName: "Adobe Creative Cloud Student" },
};

const ANNUAL_SAVINGS: Record<string, number> = {
  netflix: 20,
  spotify: 14,
  "disney+": 28,
  hulu: 16,
  "apple tv+": 20,
  youtube: 24,
  adobe: 40,
  canva: 44,
  dropbox: 20,
  evernote: 20,
  notion: 16,
};

type Insight = {
  type: "cancel" | "keep" | "switch_plan" | "student" | "streaming" | "annual" | "trial" | "travel" | "price" | "risk";
  priority: "critical" | "high" | "medium" | "low";
  title: string;
  body: string;
  action: string;
  savingsJmd?: number;
  confidence?: number;
};

function deriveInsights(
  analysis: SubscriptionAnalysis | null,
  renewalSubs: RenewalSub[],
  calendarRecs: CalendarRec[],
  isStudent: boolean,
  exchangeRate: number
): Insight[] {
  const insights: Insight[] = [];
  if (!analysis) return insights;

  const subs = analysis.subscriptions ?? [];

  // ── Trial alerts → cancel recommendation ──
  (analysis.trial_alerts ?? []).forEach((t) => {
    insights.push({
      type: "trial",
      priority: "critical",
      title: `Cancel "${t.merchant}" before trial converts`,
      body: `Trial score ${Math.round(t.trial_score * 100)}%. First charge was $${t.first_charge.toFixed(2)}, now $${t.current_charge.toFixed(2)}. ${t.description}`,
      action: `Cancel ${t.merchant} before next billing date`,
      confidence: t.trial_score,
    });
  });

  // ── Price increases ──
  (analysis.price_changes ?? [])
    .filter((c) => c.type === "price_increase")
    .forEach((c) => {
      const annualExtraCost = c.change_amount * 12;
      insights.push({
        type: "price",
        priority: "high",
        title: `${c.subscription} raised its price by ${c.change_percent}%`,
        body: `Price went from $${c.old_amount.toFixed(2)} to $${c.new_amount.toFixed(2)} on ${c.date}. That's an extra $${annualExtraCost.toFixed(2)}/year.`,
        action: `Review whether ${c.subscription} is still worth the higher price`,
        savingsJmd: Math.round(annualExtraCost * exchangeRate),
      });
    });

  // ── Streaming consolidation ──
  const streamingSubs = subs.filter((s) =>
    STREAMING_NAMES.has(s.merchant.toLowerCase().replace(/\s*\(.*\)/, "").trim())
  );
  if (streamingSubs.length > 1) {
    const totalMonthly = streamingSubs.reduce((sum, s) => sum + s.amount, 0);
    insights.push({
      type: "streaming",
      priority: "high",
      title: `You have ${streamingSubs.length} streaming services — consider consolidating`,
      body: `${streamingSubs.map((s) => s.merchant).join(", ")} total $${totalMonthly.toFixed(2)}/mo. Most households use 1–2. Cancelling the least-watched could save ~$${(totalMonthly * 0.4).toFixed(2)}/mo.`,
      action: "Cancel the streaming service you use least",
      savingsJmd: Math.round(totalMonthly * 0.4 * 12 * exchangeRate),
    });
  }

  // ── Student plan suggestions ──
  if (isStudent) {
    subs.forEach((s) => {
      const key = Object.keys(STUDENT_ELIGIBLE).find((k) =>
        s.merchant.toLowerCase().includes(k)
      );
      if (!key) return;
      const info = STUDENT_ELIGIBLE[key];
      const savingsPerMonth = s.amount * (info.discount / 100);
      insights.push({
        type: "student",
        priority: "high",
        title: `Switch ${s.merchant} to the student plan`,
        body: `You're marked as a student but appear to be on a standard plan. ${info.planName} could save you ~${info.discount}% — approximately $${savingsPerMonth.toFixed(2)}/mo.`,
        action: `Apply for the ${info.planName} student discount`,
        savingsJmd: Math.round(savingsPerMonth * 12 * exchangeRate),
      });
    });
  }

  // ── Annual plan savings (3+ consecutive months) ──
  subs.forEach((s) => {
    if ((s.charge_count ?? 0) < 3) return;
    if (s.period?.toLowerCase() !== "monthly") return;
    const key = Object.keys(ANNUAL_SAVINGS).find((k) =>
      s.merchant.toLowerCase().includes(k)
    );
    if (!key) return;
    const annualDiscount = ANNUAL_SAVINGS[key];
    const monthlySavings = s.amount * (annualDiscount / 100);
    insights.push({
      type: "annual",
      priority: "medium",
      title: `Switch ${s.merchant} to annual billing — save ${annualDiscount}%`,
      body: `You've had ${s.merchant} for ${s.charge_count}+ months. Switching to annual saves approximately $${(monthlySavings * 12).toFixed(2)}/year based on typical pricing.`,
      action: `Switch ${s.merchant} to an annual plan`,
      savingsJmd: Math.round(monthlySavings * 12 * exchangeRate),
    });
  });

  // ── High renewal risk ──
  renewalSubs
    .filter((r) => r.risk_level === "high")
    .forEach((r) => {
      insights.push({
        type: "risk",
        priority: "high",
        title: `${r.subscription} renewal is high-risk this month`,
        body: `Risk score ${Math.round(r.risk_score * 100)}%. ${r.advice} Renews on Day ${r.renewal_day}.`,
        action: `Ensure balance is sufficient before Day ${r.renewal_day}`,
        confidence: r.risk_score,
      });
    });

  // ── Calendar travel recommendations ──
  calendarRecs
    .filter((r) => r.action !== "KEEP")
    .forEach((r) => {
      insights.push({
        type: "travel",
        priority: "medium",
        title: `${r.action} ${r.subscription} while travelling to ${r.destination}`,
        body: `${r.action_detail} You'll be away for ${r.days_away} days. ${r.rationale}`,
        action: r.action_detail,
        savingsJmd: r.net_savings ? Math.round(r.net_savings * exchangeRate) : undefined,
      });
    });

  // Sort: critical → high → medium → low
  const order = { critical: 0, high: 1, medium: 2, low: 3 };
  insights.sort((a, b) => order[a.priority] - order[b.priority]);
  return insights;
}

// ─── Visual helpers ──────────────────────────────────────────────────────────

const priorityColors: Record<string, { border: string; bg: string; badge: "danger" | "warn" | "info" | "safe" }> = {
  critical: { border: "border-l-red-500", bg: "bg-red-500/5", badge: "danger" },
  high: { border: "border-l-orange-400", bg: "bg-orange-500/5", badge: "warn" },
  medium: { border: "border-l-blue-400", bg: "bg-blue-500/5", badge: "info" },
  low: { border: "border-l-green-400", bg: "bg-green-500/5", badge: "safe" },
};

const insightIcons: Record<string, React.ReactNode> = {
  trial: <AlertTriangle size={16} className="text-red-500 shrink-0" />,
  price: <TrendingUp size={16} className="text-orange-500 shrink-0" />,
  streaming: <Tv size={16} className="text-blue-500 shrink-0" />,
  student: <GraduationCap size={16} className="text-purple-500 shrink-0" />,
  annual: <DollarSign size={16} className="text-green-500 shrink-0" />,
  risk: <ShieldAlert size={16} className="text-orange-500 shrink-0" />,
  travel: <Plane size={16} className="text-blue-400 shrink-0" />,
  cancel: <XCircle size={16} className="text-red-500 shrink-0" />,
  keep: <CheckCircle size={16} className="text-green-500 shrink-0" />,
  switch_plan: <RefreshCw size={16} className="text-blue-500 shrink-0" />,
};

// ─── PDF Generation (loads jsPDF from CDN at runtime — no npm package needed) ─

async function generatePDF(
  analysis: SubscriptionAnalysis,
  insights: Insight[],
  isStudent: boolean,
  exchangeRate: number,
  localCurrency: string
) {
  type JsPDFWindow = Window & {
    jspdf?: { jsPDF: new (options: { unit: string; format: string }) => JsPDFInstance };
  };
  type JsPDFInstance = {
    setFontSize: (s: number) => void;
    setFont: (f: string, style: string) => void;
    setTextColor: (...args: number[]) => void;
    setFillColor: (...args: number[]) => void;
    setDrawColor: (...args: number[]) => void;
    text: (text: string | string[], x: number, y: number) => void;
    rect: (x: number, y: number, w: number, h: number, style: string) => void;
    line: (x1: number, y1: number, x2: number, y2: number) => void;
    addPage: () => void;
    setPage: (p: number) => void;
    getNumberOfPages: () => number;
    splitTextToSize: (text: string, maxWidth: number) => string[];
    save: (filename: string) => void;
  };

  const win = window as JsPDFWindow;

  if (!win.jspdf) {
    await new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js";
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Failed to load jsPDF"));
      document.head.appendChild(script);
    });
  }

  const doc = new win.jspdf!.jsPDF({ unit: "mm", format: "a4" });
  const pageW = 210;
  const margin = 18;
  const contentW = pageW - margin * 2;
  let y = 20;

  const addText = (
    text: string,
    size: number,
    bold = false,
    color: [number, number, number] = [30, 30, 30]
  ) => {
    doc.setFontSize(size);
    doc.setFont("helvetica", bold ? "bold" : "normal");
    doc.setTextColor(...color);
    doc.text(text, margin, y);
    y += size * 0.45 + 2;
  };

  const addLine = () => {
    doc.setDrawColor(220, 220, 220);
    doc.line(margin, y, pageW - margin, y);
    y += 5;
  };

  const checkPage = (needed = 20) => {
    if (y + needed > 275) {
      doc.addPage();
      y = 20;
    }
  };

  // Cover header
  doc.setFillColor(15, 15, 15);
  doc.rect(0, 0, 210, 40, "F");
  doc.setFontSize(22);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(255, 255, 255);
  doc.text("StatementSense", margin, 18);
  doc.setFontSize(10);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(180, 180, 180);
  doc.text("Subscription Intelligence Report", margin, 27);
  const dateStr = new Date().toLocaleDateString("en-JM", {
    day: "numeric", month: "long", year: "numeric",
  });
  doc.text(`Generated: ${dateStr}`, margin, 35);
  y = 52;

  // Summary section
  addText("Analysis Summary", 14, true);
  addLine();

  const summaryRows = [
    ["Bank Detected", analysis.bank_detected],
    ["Transactions Parsed", String(analysis.transactions_parsed)],
    ["Currency", analysis.currency],
    ["Active Subscriptions", String(analysis.summary.total_subscriptions)],
    ["Monthly Subscription Spend", `${localCurrency} $${(analysis.currency_summary?.subscription_spend_local ?? analysis.summary.total_sub_cost).toLocaleString(undefined, { minimumFractionDigits: 2 })}`],
    ["Trial Alerts", String(analysis.summary.total_trial_alerts)],
    ["Price Changes Detected", String(analysis.summary.total_price_changes)],
    ...(isStudent ? [["Student Mode", "Enabled"]] : []),
  ];

  summaryRows.forEach(([label, value]) => {
    checkPage(8);
    doc.setFontSize(9);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(100, 100, 100);
    doc.text(label, margin, y);
    doc.setFont("helvetica", "bold");
    doc.setTextColor(30, 30, 30);
    doc.text(value, margin + 80, y);
    y += 6;
  });

  y += 6;

  // Insights
  checkPage(20);
  addText("Smart Recommendations", 14, true);
  addLine();

  if (insights.length === 0) {
    addText("No actionable insights found. Your subscription portfolio looks healthy.", 9, false, [100, 100, 100]);
    y += 4;
  }

  insights.forEach((insight, i) => {
    checkPage(30);
    const priorityColor: [number, number, number] =
      insight.priority === "critical" ? [200, 40, 40]
      : insight.priority === "high" ? [220, 110, 30]
      : insight.priority === "medium" ? [30, 100, 200]
      : [40, 150, 80];

    doc.setFillColor(...priorityColor);
    doc.rect(margin, y - 2, 2.5, 10, "F");

    doc.setFontSize(9);
    doc.setFont("helvetica", "bold");
    doc.setTextColor(30, 30, 30);
    const titleLines = doc.splitTextToSize(`${i + 1}. ${insight.title}`, contentW - 10);
    doc.text(titleLines, margin + 6, y + 2);
    y += titleLines.length * 5 + 2;

    doc.setFont("helvetica", "normal");
    doc.setTextColor(80, 80, 80);
    const bodyLines = doc.splitTextToSize(insight.body, contentW - 6);
    bodyLines.forEach((line: string) => {
      checkPage(6);
      doc.text(line, margin + 6, y);
      y += 4.5;
    });

    doc.setFont("helvetica", "bold");
    doc.setTextColor(...priorityColor);
    const actionLines = doc.splitTextToSize(`-> ${insight.action}`, contentW - 6);
    actionLines.forEach((line: string) => {
      checkPage(6);
      doc.text(line, margin + 6, y);
      y += 4.5;
    });

    if (insight.savingsJmd) {
      doc.setFont("helvetica", "normal");
      doc.setTextColor(40, 150, 80);
      doc.text(`Potential annual saving: ${localCurrency} $${insight.savingsJmd.toLocaleString()}`, margin + 6, y);
      y += 4.5;
    }

    y += 5;
  });

  // Active subscriptions table
  checkPage(20);
  addText("Active Subscriptions", 14, true);
  addLine();

  const cols = [48, 28, 28, 22, 22];
  const headers = ["Subscription", "Amount/mo", "Period", "Renews Day", "Confidence"];
  const colX = cols.reduce<number[]>((acc, w, i) => {
    acc.push(i === 0 ? margin : acc[i - 1] + cols[i - 1]);
    return acc;
  }, []);

  doc.setFillColor(245, 245, 245);
  doc.rect(margin, y - 4, contentW, 8, "F");
  doc.setFontSize(8);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(60, 60, 60);
  headers.forEach((h, i) => doc.text(h, colX[i], y));
  y += 6;

  analysis.subscriptions.forEach((sub) => {
    checkPage(8);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(30, 30, 30);
    const row = [
      sub.merchant.length > 20 ? sub.merchant.slice(0, 18) + "..." : sub.merchant,
      `$${sub.amount.toFixed(2)}`,
      sub.period,
      sub.renewal_day ? `Day ${sub.renewal_day}` : "-",
      `${Math.round(sub.confidence * 100)}%`,
    ];
    row.forEach((val, i) => doc.text(val, colX[i], y));
    y += 5.5;
    doc.setDrawColor(235, 235, 235);
    doc.line(margin, y - 1, pageW - margin, y - 1);
  });

  y += 6;

  // Upcoming renewals
  if ((analysis.renewal_predictions ?? []).length > 0) {
    checkPage(20);
    addText("Upcoming Renewals", 14, true);
    addLine();

    analysis.renewal_predictions!.forEach((pred) => {
      checkPage(10);
      const urgency = pred.days_until_charge <= 3 ? [200, 40, 40] as [number, number, number]
        : pred.days_until_charge <= 7 ? [220, 110, 30] as [number, number, number]
        : [40, 150, 80] as [number, number, number];
      doc.setFontSize(9);
      doc.setFont("helvetica", "bold");
      doc.setTextColor(...urgency);
      doc.text(`${pred.days_until_charge}d`, margin, y);
      doc.setFont("helvetica", "normal");
      doc.setTextColor(30, 30, 30);
      doc.text(`${pred.subscription}  -  ${pred.next_charge_date}  (${pred.confidence_label} confidence)`, margin + 12, y);
      y += 6;
    });

    y += 4;
  }

  // Footer
  const totalPages = doc.getNumberOfPages();
  for (let p = 1; p <= totalPages; p++) {
    doc.setPage(p);
    doc.setFontSize(7);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(160, 160, 160);
    doc.text(
      `StatementSense Report - ${dateStr} - Page ${p} of ${totalPages} - Privacy-first: no financial data was transmitted`,
      margin,
      290
    );
  }

  doc.save(`StatementSense_Report_${new Date().toISOString().slice(0, 10)}.pdf`);
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function ReportPage() {
  const [analysis, setAnalysis] = useState<SubscriptionAnalysis | null>(null);
  const [renewalSubs, setRenewalSubs] = useState<RenewalSub[]>([]);
  const [calendarRecs, setCalendarRecs] = useState<CalendarRec[]>([]);
  const [isStudent, setIsStudent] = useState(false);
  const [exchangeRate, setExchangeRate] = useState(157);
  const [localCurrency, setLocalCurrency] = useState("JMD");
  const [generating, setGenerating] = useState(false);
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const pdfStarted = useRef(false);

  /* eslint-disable react-hooks/set-state-in-effect -- LocalStorage-backed report data is hydrated after mount to avoid SSR mismatches. */
  useEffect(() => {
    const savedAnalysis = readSubscriptionAnalysis<SubscriptionAnalysis>();
    if (savedAnalysis) {
      setAnalysis(savedAnalysis);
      if (savedAnalysis.currency_summary?.exchange_rate) {
        setExchangeRate(savedAnalysis.currency_summary.exchange_rate);
      }
      if (savedAnalysis.currency_summary?.original_currency) {
        setLocalCurrency(savedAnalysis.currency_summary.original_currency);
      }
    }

    const sourceSignature = subscriptionAnalysisSignature(savedAnalysis);
    const sharedSourceSignature = sharedSubscriptionsSignature(readSharedSubscriptions());
    const renewalSession = readPageSession<{
      sourceSignature?: string;
      results: { subscriptions?: RenewalSub[] };
    }>("renewal");
    if (
      renewalSession?.results?.subscriptions &&
      renewalSession.sourceSignature === sourceSignature
    ) {
      setRenewalSubs(renewalSession.results.subscriptions);
    }

    const calSession = readPageSession<{
      sourceSignature?: string;
      savingsResult?: { recommendations?: CalendarRec[] };
    }>("calendar");
    if (
      calSession?.savingsResult?.recommendations &&
      calSession.sourceSignature === sharedSourceSignature
    ) {
      setCalendarRecs(calSession.savingsResult.recommendations);
    }

    const prefs = readUserPreferences();
    if (prefs) {
      setIsStudent(prefs.isStudent);
    }
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  const insights = useMemo(
    () => deriveInsights(analysis, renewalSubs, calendarRecs, isStudent, exchangeRate),
    [analysis, renewalSubs, calendarRecs, isStudent, exchangeRate]
  );

  const handleDownload = async () => {
    if (!analysis || pdfStarted.current) return;
    pdfStarted.current = true;
    setGenerating(true);
    try {
      await generatePDF(analysis, insights, isStudent, exchangeRate, localCurrency);
    } finally {
      setGenerating(false);
      pdfStarted.current = false;
    }
  };

  const filteredInsights = activeFilter === "all"
    ? insights
    : insights.filter((i) => i.type === activeFilter || i.priority === activeFilter);

  const totalPotentialSavingsJmd = insights.reduce((sum, i) => sum + (i.savingsJmd ?? 0), 0);
  const criticalCount = insights.filter((i) => i.priority === "critical").length;
  const highCount = insights.filter((i) => i.priority === "high").length;

  const filterOptions = [
    { value: "all", label: "All" },
    { value: "critical", label: "Critical" },
    { value: "high", label: "High" },
    { value: "trial", label: "Trials" },
    { value: "streaming", label: "Streaming" },
    { value: "student", label: "Student" },
    { value: "annual", label: "Annual" },
    { value: "travel", label: "Travel" },
    { value: "risk", label: "Risk" },
  ];

  const hasSomeData = !!analysis;

  return (
    <>
      <Navbar />
      <main className="max-w-6xl mx-auto px-8 pt-32 pb-12">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-8 flex flex-col md:flex-row md:items-end md:justify-between gap-4"
        >
          <div>
            <h1 className="font-light text-4xl md:text-5xl tracking-tighter leading-tight mb-2">
              Report
            </h1>
            <p className="text-muted-foreground">
              Consolidated subscription intelligence across all senses.
              {isStudent && (
                <span className="ml-2 inline-flex items-center gap-1 text-purple-600 dark:text-purple-400 text-sm font-medium">
                  <GraduationCap size={14} /> Student mode on
                </span>
              )}
            </p>
          </div>

          {hasSomeData && (
            <button
              onClick={handleDownload}
              disabled={generating}
              className="inline-flex items-center gap-2 px-5 py-3 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl font-medium transition-colors shadow-sm disabled:opacity-60 disabled:cursor-not-allowed shrink-0"
            >
              {generating ? (
                <>
                  <RefreshCw size={16} className="animate-spin" />
                  Generating PDF...
                </>
              ) : (
                <>
                  <Download size={16} />
                  Download PDF Report
                </>
              )}
            </button>
          )}
        </motion.div>

        <AnimatePresence mode="wait">
          {!hasSomeData ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              className="max-w-lg mx-auto"
            >
              <MotionCard hover={false} className="text-center py-16">
                <FileText size={48} className="text-muted-foreground mx-auto mb-5" />
                <h2 className="text-xl font-medium mb-3">No Data Yet</h2>
                <p className="text-sm text-muted-foreground mb-6 max-w-xs mx-auto">
                  Upload a bank statement in SubscriptionSense first. The report pulls data from all
                  senses automatically.
                </p>
                <div className="flex flex-col gap-2 max-w-xs mx-auto">
                  <a
                    href="/subscription"
                    className="flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                  >
                    <ArrowRight size={15} />
                    Go to SubscriptionSense
                  </a>
                  <a
                    href="/renewal"
                    className="flex items-center justify-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium hover:bg-secondary"
                  >
                    Go to RenewalSense
                  </a>
                  <a
                    href="/calendar"
                    className="flex items-center justify-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium hover:bg-secondary"
                  >
                    Go to CalendarSense
                  </a>
                </div>
              </MotionCard>
            </motion.div>
          ) : (
            <motion.div
              key="report"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="flex flex-col gap-6"
            >
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  {
                    label: "Subscriptions",
                    value: analysis.summary.total_subscriptions,
                    color: "text-foreground",
                  },
                  {
                    label: `Monthly (${localCurrency})`,
                    value: `$${(analysis.currency_summary?.subscription_spend_local ?? analysis.summary.total_sub_cost).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
                    color: "text-yellow-600 dark:text-yellow-500",
                  },
                  {
                    label: "Recommendations",
                    value: insights.length,
                    color: criticalCount > 0 ? "text-red-600 dark:text-red-400" : "text-foreground",
                  },
                  {
                    label: `Potential Annual Saving (${localCurrency})`,
                    value: `$${totalPotentialSavingsJmd.toLocaleString()}`,
                    color: "text-green-600 dark:text-green-400",
                  },
                ].map(({ label, value, color }, i) => (
                  <motion.div
                    key={label}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.07 }}
                    className="rounded-xl bg-secondary border border-border px-4 py-4"
                  >
                    <p className="text-xs text-muted-foreground mb-1">{label}</p>
                    <p className={`text-xl font-medium ${color}`}>{value}</p>
                  </motion.div>
                ))}
              </div>

              {criticalCount > 0 && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2 }}
                  className="flex items-center gap-3 px-5 py-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-700 dark:text-red-400"
                >
                  <AlertTriangle size={18} className="shrink-0" />
                  <p className="text-sm font-medium">
                    {criticalCount} critical action{criticalCount > 1 ? "s" : ""} detected — likely trial conversions. Act before the next billing date.
                  </p>
                </motion.div>
              )}

              <MotionCard hover={false} delay={0.1}>
                <h3 className="font-medium mb-3 text-[0.95rem] flex items-center gap-2">
                  <Info size={15} />
                  Data Sources
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  {[
                    {
                      label: "SubscriptionSense",
                      active: !!analysis,
                      detail: analysis ? `${analysis.summary.total_subscriptions} subs detected` : "No data",
                    },
                    {
                      label: "RenewalSense",
                      active: renewalSubs.length > 0,
                      detail: renewalSubs.length > 0 ? `${renewalSubs.length} risk scores` : "Not run yet",
                    },
                    {
                      label: "CalendarSense",
                      active: calendarRecs.length > 0,
                      detail: calendarRecs.length > 0 ? `${calendarRecs.length} travel recs` : "Not run yet",
                    },
                    {
                      label: "Student Mode",
                      active: isStudent,
                      detail: isStudent ? "Student plan checks enabled" : "Off — set in SubscriptionSense",
                    },
                  ].map(({ label, active, detail }) => (
                    <div key={label} className="flex items-start gap-2 p-3 rounded-lg bg-secondary border border-border">
                      {active ? (
                        <CheckCircle size={14} className="text-green-600 dark:text-green-400 mt-0.5 shrink-0" />
                      ) : (
                        <Info size={14} className="text-muted-foreground mt-0.5 shrink-0" />
                      )}
                      <div>
                        <p className="font-medium text-xs">{label}</p>
                        <p className="text-xs text-muted-foreground">{detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </MotionCard>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="flex flex-col gap-4 md:col-span-2">
                  <div className="flex items-center justify-between">
                    <h2 className="text-xl font-medium flex items-center gap-2">
                      <Sparkles size={18} />
                      Smart Recommendations
                    </h2>
                    <span className="text-xs text-muted-foreground">
                      {criticalCount > 0 && (
                        <span className="text-red-600 dark:text-red-400 font-medium mr-2">
                          {criticalCount} critical
                        </span>
                      )}
                      {highCount > 0 && (
                        <span className="text-orange-500 font-medium">
                          {highCount} high
                        </span>
                      )}
                    </span>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {filterOptions.map((opt) => (
                      <button
                        key={opt.value}
                        onClick={() => setActiveFilter(opt.value)}
                        className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                          activeFilter === opt.value
                            ? "bg-primary text-primary-foreground border-primary"
                            : "border-border text-muted-foreground hover:bg-secondary"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>

                  {filteredInsights.length === 0 && (
                    <MotionCard hover={false} className="text-center py-10">
                      <CheckCircle size={36} className="text-green-500 mx-auto mb-3" />
                      <p className="text-sm font-medium">No recommendations in this category.</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {activeFilter === "all" ? "Your subscription portfolio looks healthy." : "Try a different filter."}
                      </p>
                    </MotionCard>
                  )}

                  {filteredInsights.map((insight, idx) => {
                    const colors = priorityColors[insight.priority];
                    return (
                      <MotionCard
                        key={`${insight.type}-${idx}`}
                        delay={0.05 * idx}
                        hover={false}
                        className={`border-l-[3px] ${colors.border} ${colors.bg}`}
                      >
                        <div className="flex items-start justify-between gap-3 mb-2">
                          <div className="flex items-start gap-2 flex-1">
                            {insightIcons[insight.type]}
                            <h3 className="text-sm font-medium leading-snug">{insight.title}</h3>
                          </div>
                          <Badge variant={colors.badge} className="shrink-0 capitalize text-[0.65rem]">
                            {insight.priority}
                          </Badge>
                        </div>

                        <p className="text-[0.82rem] text-muted-foreground mb-3 pl-6 leading-relaxed">
                          {insight.body}
                        </p>

                        <div className="flex flex-wrap items-center justify-between gap-2 pl-6">
                          <p className="text-[0.82rem] font-medium text-foreground flex items-center gap-1.5">
                            <ArrowRight size={13} className="shrink-0" />
                            {insight.action}
                          </p>
                          {insight.savingsJmd && (
                            <span className="text-[0.75rem] font-medium text-green-700 dark:text-green-400 bg-green-500/10 px-2 py-1 rounded-full">
                              ~{localCurrency} ${insight.savingsJmd.toLocaleString()}/yr saved
                            </span>
                          )}
                          {insight.confidence && (
                            <span className="text-[0.72rem] text-muted-foreground">
                              {Math.round(insight.confidence * 100)}% confidence
                            </span>
                          )}
                        </div>
                      </MotionCard>
                    );
                  })}
                </div>

                <div className="flex flex-col gap-4">
                  <MotionCard hover={false} delay={0.1}>
                    <h3 className="font-medium mb-3 text-[0.95rem]">All Subscriptions</h3>
                    <div className="flex flex-col gap-2">
                      {analysis.subscriptions.map((sub, i) => {
                        const renewalRisk = renewalSubs.find(
                          (r) => r.subscription.toLowerCase() === sub.merchant.toLowerCase()
                        );
                        const isTrial = analysis.trial_alerts?.some(
                          (t) => t.merchant.toLowerCase() === sub.merchant.toLowerCase()
                        );
                        return (
                          <div
                            key={i}
                            className="flex items-center justify-between py-2 border-b border-border last:border-0"
                          >
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium truncate flex items-center gap-1.5">
                                {sub.merchant}
                                {isTrial && (
                                  <AlertTriangle size={12} className="text-red-500 shrink-0" />
                                )}
                                {renewalRisk?.risk_level === "high" && (
                                  <ShieldAlert size={12} className="text-orange-400 shrink-0" />
                                )}
                              </p>
                              <p className="text-xs text-muted-foreground">
                                {sub.period} · Day {sub.renewal_day ?? "?"}
                              </p>
                            </div>
                            <p className="text-sm font-medium text-yellow-600 dark:text-yellow-500 ml-2 shrink-0">
                              ${sub.amount.toFixed(2)}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  </MotionCard>

                  {(analysis.renewal_predictions ?? []).length > 0 && (
                    <MotionCard hover={false} delay={0.15}>
                      <h3 className="font-medium mb-3 text-[0.95rem] flex items-center gap-2">
                        <Calendar size={15} />
                        Upcoming Renewals
                      </h3>
                      <div className="flex flex-col gap-2">
                        {analysis.renewal_predictions!.slice(0, 6).map((pred, i) => {
                          const urgency =
                            pred.days_until_charge <= 3
                              ? "text-red-600 dark:text-red-400"
                              : pred.days_until_charge <= 7
                              ? "text-yellow-600 dark:text-yellow-500"
                              : "text-green-600 dark:text-green-400";
                          return (
                            <div key={i} className="flex items-center gap-3 py-1.5 border-b border-border last:border-0">
                              <p className={`text-lg font-medium w-8 shrink-0 ${urgency}`}>
                                {pred.days_until_charge}d
                              </p>
                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium truncate">{pred.subscription}</p>
                                <p className="text-[0.7rem] text-muted-foreground">{pred.next_charge_date}</p>
                              </div>
                              <Badge
                                variant={
                                  pred.confidence_label === "high"
                                    ? "safe"
                                    : pred.confidence_label === "medium"
                                    ? "warn"
                                    : "danger"
                                }
                                className="text-[0.62rem]"
                              >
                                {pred.confidence_label}
                              </Badge>
                            </div>
                          );
                        })}
                      </div>
                    </MotionCard>
                  )}

                  {(analysis.price_changes ?? []).length > 0 && (
                    <MotionCard hover={false} delay={0.2} className="border-yellow-500/20 bg-yellow-500/5">
                      <h3 className="font-medium mb-3 text-[0.95rem] flex items-center gap-2">
                        <TrendingUp size={15} className="text-orange-500" />
                        Price Changes
                      </h3>
                      {analysis.price_changes!.map((change, i) => (
                        <div key={i} className="flex items-center justify-between py-1.5 border-b border-border last:border-0">
                          <div>
                            <p className="text-xs font-medium">{change.subscription}</p>
                            <p className="text-[0.7rem] text-muted-foreground">{change.date}</p>
                          </div>
                          <span
                            className={`text-xs font-medium ${
                              change.type === "price_increase"
                                ? "text-red-600 dark:text-red-400"
                                : "text-green-600 dark:text-green-400"
                            }`}
                          >
                            {change.type === "price_increase" ? "+" : ""}
                            {change.change_percent}%
                          </span>
                        </div>
                      ))}
                    </MotionCard>
                  )}

                  {calendarRecs.length > 0 && (
                    <MotionCard hover={false} delay={0.25} className="border-blue-400/20 bg-blue-500/5">
                      <h3 className="font-medium mb-3 text-[0.95rem] flex items-center gap-2">
                        <Plane size={15} className="text-blue-500" />
                        Travel Actions
                      </h3>
                      {calendarRecs.map((rec, i) => (
                        <div key={i} className="py-1.5 border-b border-border last:border-0">
                          <p className="text-xs font-medium">
                            {rec.action} {rec.subscription}
                          </p>
                          <p className="text-[0.7rem] text-muted-foreground">
                            {rec.destination} · {rec.days_away} days
                          </p>
                        </div>
                      ))}
                    </MotionCard>
                  )}

                  <button
                    onClick={handleDownload}
                    disabled={generating}
                    className="md:hidden w-full flex items-center justify-center gap-2 py-3 bg-primary text-primary-foreground rounded-xl font-medium text-sm hover:bg-primary/90 disabled:opacity-60"
                  >
                    {generating ? (
                      <RefreshCw size={15} className="animate-spin" />
                    ) : (
                      <Download size={15} />
                    )}
                    {generating ? "Generating..." : "Download PDF Report"}
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </>
  );
}
