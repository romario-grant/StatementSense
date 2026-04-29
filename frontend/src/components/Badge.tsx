import type { CSSProperties, ReactNode } from "react";

type BadgeVariant = "safe" | "low" | "warn" | "moderate" | "danger" | "high" | "critical" | "info" | "teal";

const variantStyles: Record<BadgeVariant, CSSProperties> = {
  safe: { background: "var(--status-safe-bg)", color: "var(--status-safe)" },
  low: { background: "var(--status-safe-bg)", color: "var(--status-safe)" },
  warn: { background: "var(--status-warn-bg)", color: "var(--status-warn)" },
  moderate: { background: "var(--status-warn-bg)", color: "var(--status-warn)" },
  danger: { background: "var(--status-danger-bg)", color: "var(--status-danger)" },
  high: { background: "var(--status-danger-bg)", color: "var(--status-danger)" },
  critical: { background: "var(--status-danger-bg)", color: "var(--status-danger)" },
  info: { background: "var(--accent-teal-light)", color: "var(--accent-teal)" },
  teal: { background: "var(--accent-teal-light)", color: "var(--accent-teal)" },
};

interface BadgeProps {
  variant: BadgeVariant;
  children: ReactNode;
  style?: CSSProperties;
}

export default function Badge({ variant, children, style }: BadgeProps) {
  return (
    <span
      className="badge"
      style={{ ...variantStyles[variant], ...style }}
    >
      {children}
    </span>
  );
}
