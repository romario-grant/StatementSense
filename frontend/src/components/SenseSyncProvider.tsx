"use client";

// Background coordinator that, after a SubscriptionSense analysis completes, automatically pre-warms RenewalSense and CalendarSense data so the corresponding pages can render instantly when the user navigates to them.

import { useCallback, useEffect, useRef, type ReactNode } from "react";
import { useAuth } from "@/components/AuthProvider";
import { readPageSession, savePageSession } from "@/lib/pageSessionStore";
import {
  readSharedSubscriptions,
  readSubscriptionAnalysis,
  sharedSubscriptionsSignature,
  subscriptionAnalysisSignature,
  type SharedSubscription,
} from "@/lib/subscriptionStore";
import {
  saveSenseSyncStatus,
  SUBSCRIPTION_SOURCE_CHANGED_EVENT,
} from "@/lib/senseSyncStore";

const FALLBACK_BACKEND_URL =
  "https://statementsense-backend-430268251728.us-central1.run.app";
const SYNC_DEBOUNCE_MS = 900;

type SavedSubscriptionAnalysis = {
  transactions?: Record<string, unknown>[];
  subscriptions?: Record<string, unknown>[];
  price_changes?: Record<string, unknown>[];
  transactions_parsed?: number;
  currency_summary?: {
    exchange_rate?: number;
    exchange_rate_source?: string;
    original_currency?: string;
  };
};

type CalendarSession = {
  sourceSignature?: string;
  homeLocation?: string;
  subscriptions?: { id: number; name: string; cost: string; renewalDay: string }[];
  events?: Record<string, unknown>[] | null;
  eventsPreview?: Record<string, unknown>[];
  eventsCount?: number;
  classifyResult?: Record<string, unknown>;
  savingsResult?: Record<string, unknown>;
  remindersResult?: Record<string, unknown>;
};

type PlanSimulatorState = {
  loading: boolean;
  error: string | null;
  data?: Record<string, unknown>;
  selectedIndex: number;
  expanded: boolean;
};

const apiBase = () =>
  process.env.NODE_ENV === "production"
    ? (process.env.NEXT_PUBLIC_BACKEND_URL || FALLBACK_BACKEND_URL).replace(/\/$/, "")
    : "";

const currentMonth = () => {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
};

const toCalendarInputs = (subscriptions: SharedSubscription[]) =>
  subscriptions
    .filter((sub) => sub.name && sub.cost > 0)
    .map((sub, index) => ({
      id: sub.id || Date.now() + index,
      name: sub.name,
      cost: sub.cost.toString(),
      renewalDay: sub.renewalDay ? String(sub.renewalDay) : "",
    }));

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok || data?.error) {
    const detail = data?.detail && typeof data.detail === "object" ? data.detail : data;
    throw new Error(detail?.error || data?.detail || data?.error || "Background sync failed.");
  }
  return data as T;
}

async function runRenewalSync(source: SavedSubscriptionAnalysis, sourceSignature: string) {
  if (!source.transactions?.length) {
    return { status: "skipped" as const, message: "No parsed transactions available." };
  }

  const { year, month } = currentMonth();
  const data = await postJson<Record<string, unknown>>("/api/renewal/analyze-existing", {
    transactions: source.transactions || [],
    subscriptions: source.subscriptions || [],
    price_changes: source.price_changes || [],
    year,
    month,
  });

  const subscriptions = Array.isArray(data.subscriptions)
    ? (data.subscriptions as Record<string, unknown>[])
    : [];
  const planResults = await Promise.allSettled(
    subscriptions.map((sub) =>
      postJson<Record<string, unknown>>("/api/renewal/plan-simulator", {
        subscription: sub,
        salary: data.salary || {},
        expenses: data.expenses || [],
        transactions: data.transactions || [],
        year,
        month,
        exchange_rate: source.currency_summary?.exchange_rate || null,
        exchange_rate_source: source.currency_summary?.exchange_rate_source || null,
        country:
          (source.currency_summary?.original_currency || "JMD") === "JMD"
            ? "Jamaica"
            : "United States",
        local_currency: source.currency_summary?.original_currency || "JMD",
      })
    )
  );
  const planSimulators = planResults.reduce<Record<string, PlanSimulatorState>>(
    (acc, result, index) => {
      const sub = subscriptions[index];
      const name = String(sub?.subscription || sub?.merchant || sub?.name || `Plan ${index + 1}`);
      const key = `${name}-${index}`;
      acc[key] = {
        loading: false,
        error:
          result.status === "rejected"
            ? result.reason?.message || "Plan comparison failed."
            : null,
        data: result.status === "fulfilled" ? result.value : undefined,
        selectedIndex: 0,
        expanded: false,
      };
      return acc;
    },
    {}
  );

  savePageSession("renewal", {
    results: data,
    sourceSignature,
    hasSourceAnalysis: true,
    exchangeRate: source.currency_summary?.exchange_rate || null,
    exchangeRateSource: source.currency_summary?.exchange_rate_source || null,
    localCurrency: source.currency_summary?.original_currency || "JMD",
    planSimulators,
  });
  return { status: "complete" as const };
}

async function loadCalendarEvents(saved: CalendarSession | null) {
  if (saved?.events?.length) {
    return {
      events: saved.events,
      eventsPreview: saved.eventsPreview || [],
      eventsCount: saved.eventsCount || saved.events.length,
    };
  }

  const token = localStorage.getItem("google_access_token") || "";
  if (!token) {
    return null;
  }

  const data = await postJson<{
    events: Record<string, unknown>[];
    events_preview?: Record<string, unknown>[];
    events_scanned?: number;
  }>("/api/calendar/events", { access_token: token });

  return {
    events: data.events || [],
    eventsPreview: data.events_preview || [],
    eventsCount: data.events_scanned || data.events?.length || 0,
  };
}

async function runCalendarSync(
  source: SavedSubscriptionAnalysis | null,
  subscriptions: SharedSubscription[],
  calendarSignature: string
) {
  if (subscriptions.length === 0) {
    return { status: "skipped" as const, message: "No subscriptions available." };
  }

  const saved = readPageSession<CalendarSession>("calendar");
  const loadedEvents = await loadCalendarEvents(saved);
  if (!loadedEvents?.events?.length) {
    return { status: "skipped" as const, message: "Google Calendar events are not available." };
  }

  const homeLocation = saved?.homeLocation || "Kingston, Jamaica";
  const subscriptionInputs = toCalendarInputs(subscriptions);
  const classifyResult = await postJson<Record<string, unknown>>("/api/calendar/classify", {
    events: loadedEvents.events,
    home_location: homeLocation,
    subscriptions: subscriptionInputs.map((sub) => ({
      name: sub.name,
      cost: parseFloat(sub.cost),
      renewal_day: sub.renewalDay ? parseInt(sub.renewalDay, 10) : null,
    })),
  });

  let savingsResult: Record<string, unknown> | null = null;
  const localCount = Number(classifyResult.local_count || 0);
  const awayPeriods = Array.isArray(classifyResult.away_periods)
    ? classifyResult.away_periods
    : [];
  if (localCount > 0 && awayPeriods.length > 0) {
    savingsResult = await postJson<Record<string, unknown>>("/api/calendar/savings", {
      away_periods: awayPeriods,
      processed_subscriptions: classifyResult.processed_subscriptions || [],
      local_currency: source?.currency_summary?.original_currency || "JMD",
      exchange_rate: source?.currency_summary?.exchange_rate || null,
    });
  }

  savePageSession("calendar", {
    sourceSignature: calendarSignature,
    homeLocation,
    subscriptions: subscriptionInputs,
    events: loadedEvents.events,
    eventsPreview: loadedEvents.eventsPreview,
    eventsCount: loadedEvents.eventsCount,
    classifyResult,
    savingsResult,
    remindersResult: saved?.remindersResult || null,
  });

  return { status: "complete" as const };
}

export default function SenseSyncProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const timerRef = useRef<number | null>(null);
  const runningSignatureRef = useRef<string | null>(null);

  const runSync = useCallback(async () => {
    if (!user) return;

    const source = readSubscriptionAnalysis<SavedSubscriptionAnalysis>();
    const subscriptions = readSharedSubscriptions();
    const renewalSignature = subscriptionAnalysisSignature(source);
    const calendarSignature = sharedSubscriptionsSignature(subscriptions);
    const combinedSignature = JSON.stringify({
      renewal: renewalSignature,
      calendar: calendarSignature,
    });

    if (!source || !renewalSignature || subscriptions.length === 0) return;
    if (runningSignatureRef.current === combinedSignature) return;

    const renewalSession = readPageSession<{ sourceSignature?: string }>("renewal");
    const calendarSession = readPageSession<{ sourceSignature?: string }>("calendar");
    const needsRenewal = renewalSession?.sourceSignature !== renewalSignature;
    const needsCalendar = calendarSession?.sourceSignature !== calendarSignature;
    if (!needsRenewal && !needsCalendar) return;

    runningSignatureRef.current = combinedSignature;
    saveSenseSyncStatus({
      sourceSignature: combinedSignature,
      status: "running",
      startedAt: new Date().toISOString(),
      renewal: { status: needsRenewal ? "running" : "skipped" },
      calendar: { status: needsCalendar ? "running" : "skipped" },
    });

    const [renewal, calendar] = await Promise.allSettled([
      needsRenewal
        ? runRenewalSync(source, renewalSignature)
        : Promise.resolve({ status: "skipped" as const }),
      needsCalendar
        ? runCalendarSync(source, subscriptions, calendarSignature)
        : Promise.resolve({ status: "skipped" as const }),
    ]);

    const renewalStatus =
      renewal.status === "fulfilled"
        ? renewal.value
        : { status: "error" as const, message: renewal.reason?.message || "Renewal sync failed." };
    const calendarStatus =
      calendar.status === "fulfilled"
        ? calendar.value
        : { status: "error" as const, message: calendar.reason?.message || "Calendar sync failed." };
    const hasError = renewalStatus.status === "error" || calendarStatus.status === "error";
    const hasComplete = renewalStatus.status === "complete" || calendarStatus.status === "complete";

    saveSenseSyncStatus({
      sourceSignature: combinedSignature,
      status: hasError ? (hasComplete ? "partial" : "error") : "complete",
      completedAt: new Date().toISOString(),
      renewal: renewalStatus,
      calendar: calendarStatus,
    });
    runningSignatureRef.current = null;
  }, [user]);

  const scheduleSync = useCallback(() => {
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
    }
    timerRef.current = window.setTimeout(() => {
      void runSync();
    }, SYNC_DEBOUNCE_MS);
  }, [runSync]);

  useEffect(() => {
    if (!user) return;
    scheduleSync();
    const onStorage = (event: StorageEvent) => {
      if (event.key?.startsWith("statementsense.")) scheduleSync();
    };
    window.addEventListener(SUBSCRIPTION_SOURCE_CHANGED_EVENT, scheduleSync);
    window.addEventListener("storage", onStorage);
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
      window.removeEventListener(SUBSCRIPTION_SOURCE_CHANGED_EVENT, scheduleSync);
      window.removeEventListener("storage", onStorage);
    };
  }, [scheduleSync, user]);

  return <>{children}</>;
}
