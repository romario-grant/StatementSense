const keyFor = (name: string) => `statementsense.${name}.session`;

export const readPageSession = <T>(name: string): T | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(keyFor(name));
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
};

export const savePageSession = (name: string, data: unknown) => {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(keyFor(name), JSON.stringify(data));
};

export const clearPageSession = (name: string) => {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(keyFor(name));
};

export const clearAllPageSessions = () => {
  if (typeof window === "undefined") return;
  ["renewal", "screentime", "calendar"].forEach((name) => {
    window.localStorage.removeItem(keyFor(name));
  });
};
