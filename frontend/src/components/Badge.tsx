import type { CSSProperties, ReactNode } from "react";

type BadgeVariant = "safe" | "low" | "warn" | "moderate" | "danger" | "high" | "critical" | "info" | "teal";

const variantClasses: Record<BadgeVariant, string> = {
  safe: "bg-green-500/15 text-green-700 dark:text-green-400",
  low: "bg-green-500/15 text-green-700 dark:text-green-400",
  warn: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  moderate: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  danger: "bg-red-500/15 text-red-700 dark:text-red-400",
  high: "bg-red-500/15 text-red-700 dark:text-red-400",
  critical: "bg-red-500/15 text-red-700 dark:text-red-400",
  info: "bg-secondary text-foreground dark:text-foreground",
  teal: "bg-secondary text-foreground dark:text-foreground",
};

interface BadgeProps {
  variant: BadgeVariant;
  children: ReactNode;
  style?: CSSProperties;
  className?: string;
}

export default function Badge({ variant, children, style, className = "" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold tracking-wide ${variantClasses[variant]} ${className}`}
      style={style}
    >
      {children}
    </span>
  );
}
