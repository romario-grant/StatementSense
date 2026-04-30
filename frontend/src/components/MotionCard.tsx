"use client";

import { motion } from "framer-motion";
import type { ReactNode, CSSProperties } from "react";

interface MotionCardProps {
  children: ReactNode;
  className?: string;
  delay?: number;
  style?: CSSProperties;
  hover?: boolean;
  onClick?: () => void;
}

export default function MotionCard({
  children,
  className = "",
  delay = 0,
  style,
  hover = true,
  onClick,
}: MotionCardProps) {
  return (
    <motion.div
      className={`bg-card text-card-foreground border border-border rounded-2xl p-6 shadow-sm transition-colors ${className}`}
      style={style}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.5,
        delay,
        ease: [0.25, 0.1, 0.25, 1],
      }}
      whileHover={
        hover
          ? {
              y: -4,
              boxShadow: "0 8px 30px rgba(0, 0, 0, 0.12)",
              transition: { duration: 0.25 },
            }
          : undefined
      }
      onClick={onClick}
    >
      {children}
    </motion.div>
  );
}
