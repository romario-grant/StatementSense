export const SUBSCRIPTION_SOURCE_CHANGED_EVENT = "statementsense:subscription-source-changed";
export const SENSE_SYNC_UPDATED_EVENT = "statementsense:sense-sync-updated";

export type SenseSyncStatus = {
  sourceSignature: string | null;
  status: "idle" | "running" | "complete" | "partial" | "error";
  startedAt?: string;
  completedAt?: string;
  renewal?: {
    status: "skipped" | "running" | "complete" | "error";
    message?: string;
  };
  calendar?: {
    status: "skipped" | "running" | "complete" | "error";
    message?: string;
  };
};

const STORAGE_KEY = "statementsense.reportSync.session";

export const notifySubscriptionSourceChanged = () => {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(SUBSCRIPTION_SOURCE_CHANGED_EVENT));
};

export const notifySenseSyncUpdated = () => {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(SENSE_SYNC_UPDATED_EVENT));
};

export const readSenseSyncStatus = (): SenseSyncStatus | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as SenseSyncStatus) : null;
  } catch {
    return null;
  }
};

export const saveSenseSyncStatus = (status: SenseSyncStatus) => {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(status));
  notifySenseSyncUpdated();
};
