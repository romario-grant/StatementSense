export type SharedSubscription = {
  id: number;
  name: string;
  cost: number;
  renewalDay?: number | null;
  period?: string;
  bank?: string;
  source?: "subscription-sense" | "manual";
};

type SubscriptionAnalysisSignatureSource = {
  transactions?: unknown[];
  transactions_parsed?: number;
  subscriptions?: Record<string, unknown>[];
  price_changes?: Record<string, unknown>[];
};

const STORAGE_KEY = "statementsense.subscriptions";
const ANALYSIS_STORAGE_KEY = "statementsense.subscriptionAnalysis";

const parseNumber = (value: unknown): number => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value.replace(/[^0-9.-]/g, ""));
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

export const readSharedSubscriptions = (): SharedSubscription[] => {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item, index) => ({
        id: parseNumber(item.id) || Date.now() + index,
        name: String(item.name || "").trim(),
        cost: parseNumber(item.cost),
        renewalDay:
          item.renewalDay === null || item.renewalDay === undefined
            ? null
            : parseNumber(item.renewalDay),
        period: item.period ? String(item.period) : undefined,
        bank: item.bank ? String(item.bank) : undefined,
        source: (item.source === "manual"
          ? "manual"
          : "subscription-sense") as SharedSubscription["source"],
      }))
      .filter((item) => item.name && item.cost > 0);
  } catch {
    return [];
  }
};

export const saveSharedSubscriptions = (subscriptions: SharedSubscription[]) => {
  if (typeof window === "undefined") return;

  const unique = new Map<string, SharedSubscription>();
  subscriptions.forEach((sub, index) => {
    const name = sub.name.trim();
    if (!name || !Number.isFinite(sub.cost) || sub.cost <= 0) return;
    unique.set(name.toLowerCase(), {
      id: sub.id || Date.now() + index,
      name,
      cost: Number(sub.cost.toFixed(2)),
      renewalDay: sub.renewalDay ?? null,
      period: sub.period,
      bank: sub.bank,
      source: sub.source ?? "subscription-sense",
    });
  });

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...unique.values()]));
};

export const sharedSubscriptionsSignature = (subscriptions: SharedSubscription[]) =>
  JSON.stringify(
    subscriptions.map((sub) => ({
      name: sub.name,
      cost: sub.cost,
      renewalDay: sub.renewalDay ?? null,
      period: sub.period || "",
      bank: sub.bank || "",
      source: sub.source || "subscription-sense",
    }))
  );

export const subscriptionAnalysisSignature = (
  source: SubscriptionAnalysisSignatureSource | null
) => {
  if (!source) return null;
  return JSON.stringify({
    transactionsParsed: source.transactions_parsed || source.transactions?.length || 0,
    subscriptions: (source.subscriptions || []).map((sub) => ({
      merchant: sub.merchant || sub.name || sub.subscription,
      amount: sub.amount,
      period: sub.period,
      renewalDay: sub.renewal_day || sub.renewalDay,
      lastCharge: sub.last_charge,
      source: sub.source,
    })),
    priceChanges: (source.price_changes || []).map((change) => ({
      subscription: change.subscription,
      type: change.type,
      date: change.date,
      newAmount: change.new_amount,
    })),
  });
};

export const readSubscriptionAnalysis = <T>(): T | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(ANALYSIS_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
};

export const saveSubscriptionAnalysis = (analysis: unknown) => {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ANALYSIS_STORAGE_KEY, JSON.stringify(analysis));
};

export const clearSubscriptionAnalysis = () => {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ANALYSIS_STORAGE_KEY);
};

export const clearSubscriptionSession = () => {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.localStorage.removeItem(ANALYSIS_STORAGE_KEY);
};
