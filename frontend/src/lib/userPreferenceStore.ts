export type BudgetingStyle = "strict" | "balanced" | "lenient";

export type UserPreferences = {
  budgetingStyle: BudgetingStyle;
  styleMultiplier: number;
  isStudent: boolean;
  monthlySubscriptionCapJmd: number | null;
};

const STORAGE_KEY = "statementsense.userPreferences";

export const BUDGETING_STYLES: Record<
  BudgetingStyle,
  { label: string; styleMultiplier: number }
> = {
  strict: { label: "Strict", styleMultiplier: 0.07 },
  balanced: { label: "Balanced", styleMultiplier: 0.1 },
  lenient: { label: "Lenient", styleMultiplier: 0.15 },
};

export const DEFAULT_USER_PREFERENCES: UserPreferences = {
  budgetingStyle: "balanced",
  styleMultiplier: BUDGETING_STYLES.balanced.styleMultiplier,
  isStudent: false,
  monthlySubscriptionCapJmd: null,
};

export const readUserPreferences = (): UserPreferences | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<UserPreferences>;
    const budgetingStyle: BudgetingStyle =
      typeof parsed.budgetingStyle === "string" &&
      parsed.budgetingStyle in BUDGETING_STYLES
        ? (parsed.budgetingStyle as BudgetingStyle)
        : DEFAULT_USER_PREFERENCES.budgetingStyle;
    const cap =
      typeof parsed.monthlySubscriptionCapJmd === "number" &&
      Number.isFinite(parsed.monthlySubscriptionCapJmd) &&
      parsed.monthlySubscriptionCapJmd > 0
        ? parsed.monthlySubscriptionCapJmd
        : null;

    return {
      budgetingStyle,
      styleMultiplier: BUDGETING_STYLES[budgetingStyle].styleMultiplier,
      isStudent: Boolean(parsed.isStudent),
      monthlySubscriptionCapJmd: cap,
    };
  } catch {
    return null;
  }
};

export const saveUserPreferences = (preferences: UserPreferences) => {
  if (typeof window === "undefined") return;
  const budgetingStyle =
    preferences.budgetingStyle in BUDGETING_STYLES
      ? preferences.budgetingStyle
      : DEFAULT_USER_PREFERENCES.budgetingStyle;

  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      budgetingStyle,
      styleMultiplier: BUDGETING_STYLES[budgetingStyle].styleMultiplier,
      isStudent: Boolean(preferences.isStudent),
      monthlySubscriptionCapJmd:
        preferences.monthlySubscriptionCapJmd &&
        Number.isFinite(preferences.monthlySubscriptionCapJmd) &&
        preferences.monthlySubscriptionCapJmd > 0
          ? preferences.monthlySubscriptionCapJmd
          : null,
    })
  );
};

export const clearUserPreferences = () => {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
};
