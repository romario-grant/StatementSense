"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Sun, Moon } from "lucide-react";
import { useTheme } from "./ThemeProvider";

const navLinks = [
  { path: "/renewal", label: "RenewalSense" },
  { path: "/screentime", label: "ScreentimeSense" },
  { path: "/calendar", label: "CalendarSense" },
];

export default function Navbar() {
  const pathname = usePathname();
  const [hovered, setHovered] = useState<string | null>(null);
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  const isHomePage = pathname === "/";

  return (
    <nav
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 999,
        padding: "2rem 3rem 1.25rem",
        pointerEvents: "none",
      }}
    >
      {/* ── Brand — absolute left ── */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] as const }}
        style={{ position: "absolute", left: "3rem", top: "2rem", pointerEvents: "auto" }}
      >
        <Link
          href="/"
          style={{
            color: isHomePage ? "#ffffff" : "var(--text-primary)",
            fontWeight: 700,
            fontSize: "1.05rem",
            letterSpacing: "-0.01em",
            textDecoration: "none",
            whiteSpace: "nowrap",
            lineHeight: 1,
          }}
        >
          StatementSense
        </Link>
      </motion.div>

      {/* ── Nav Links — true center ── */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] as const }}
        style={{
          width: "100%",
          display: "flex",
          justifyContent: "center",
          gap: "2rem",
          alignItems: "center",
          pointerEvents: "auto",
        }}
      >
        {navLinks.map(({ path, label }) => {
          const active = pathname === path;
          const isHovered = hovered === path;
          const showLine = active || isHovered;

          const activeColor = isHomePage ? "#ffffff" : "var(--text-primary)";
          const inactiveColor = isHomePage ? "rgba(255, 255, 255, 0.6)" : "var(--text-muted)";

          return (
            <Link
              key={path}
              href={path}
              onMouseEnter={() => setHovered(path)}
              onMouseLeave={() => setHovered(null)}
              style={{
                position: "relative",
                color: active ? activeColor : inactiveColor,
                fontWeight: 600,
                textDecoration: "none",
                paddingBottom: "4px",
                fontSize: "0.82rem",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                transition: "color 0.25s ease",
                whiteSpace: "nowrap",
                lineHeight: 1,
              }}
            >
              {label}
              <motion.span
                style={{
                  position: "absolute",
                  bottom: 0,
                  left: 0,
                  right: 0,
                  height: "2px",
                  borderRadius: "1px",
                  background: active ? activeColor : inactiveColor,
                  transformOrigin: "center",
                }}
                initial={false}
                animate={{
                  scaleX: showLine ? 1 : 0,
                  opacity: showLine ? 1 : 0,
                }}
                transition={{ duration: 0.25, ease: "easeInOut" }}
              />
            </Link>
          );
        })}
      </motion.div>

      {/* ── Theme Toggle — absolute right ── */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] as const }}
        style={{ position: "absolute", right: "3rem", top: "2rem", pointerEvents: "auto" }}
      >
        <button
          onClick={toggleTheme}
          aria-label="Toggle theme"
          style={{
            background: isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)",
            border: isDark ? "1px solid rgba(255,255,255,0.2)" : "1px solid rgba(0,0,0,0.15)",
            borderRadius: "50%",
            width: "38px",
            height: "38px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            color: "var(--text-primary)",
            transition: "border-color 0.3s, color 0.3s, background 0.3s",
            backdropFilter: "blur(12px)",
            WebkitBackdropFilter: "blur(12px)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--accent-teal)";
            e.currentTarget.style.color = "var(--accent-teal)";
            e.currentTarget.style.background = "var(--accent-teal-light)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = isDark ? "rgba(255,255,255,0.2)" : "rgba(0,0,0,0.15)";
            e.currentTarget.style.color = "var(--text-primary)";
            e.currentTarget.style.background = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";
          }}
        >
          <AnimatePresence mode="wait" initial={false}>
            {!isDark ? (
              <motion.div
                key="sun"
                initial={{ rotate: -90, opacity: 0 }}
                animate={{ rotate: 0, opacity: 1 }}
                exit={{ rotate: 90, opacity: 0 }}
                transition={{ duration: 0.3 }}
                style={{ display: "flex" }}
              >
                <Sun size={18} strokeWidth={2} />
              </motion.div>
            ) : (
              <motion.div
                key="moon"
                initial={{ rotate: 90, opacity: 0 }}
                animate={{ rotate: 0, opacity: 1 }}
                exit={{ rotate: -90, opacity: 0 }}
                transition={{ duration: 0.3 }}
                style={{ display: "flex" }}
              >
                <Moon size={18} strokeWidth={2} />
              </motion.div>
            )}
          </AnimatePresence>
        </button>
      </motion.div>
    </nav>
  );
}
