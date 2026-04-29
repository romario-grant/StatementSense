"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { LogOut } from "lucide-react";
import { useTheme } from "./ThemeProvider";
import { useAuth } from "./AuthProvider";

const navLinks = [
  { path: "/renewal", label: "RenewalSense" },
  { path: "/screentime", label: "ScreentimeSense" },
  { path: "/calendar", label: "CalendarSense" },
];

export default function Navbar() {
  const pathname = usePathname();
  const [hovered, setHovered] = useState<string | null>(null);
  const { theme, toggleTheme } = useTheme();
  const { logout } = useAuth();
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

      {/* ── Right Controls ── */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] as const }}
        style={{ position: "absolute", right: "3rem", top: "2rem", pointerEvents: "auto", display: "flex", gap: "1rem", alignItems: "center" }}
      >
        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          aria-label="Toggle theme"
          style={{
            background: "transparent",
            border: "none",
            cursor: "pointer",
            color: "var(--text-muted)",
            fontSize: "0.82rem",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            transition: "color 0.25s ease",
            padding: "0.25rem 0",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "var(--text-primary)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "var(--text-muted)";
          }}
        >
          <AnimatePresence mode="wait" initial={false}>
            {!isDark ? (
              <motion.span
                key="dark-text"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                Dark Mode
              </motion.span>
            ) : (
              <motion.span
                key="light-text"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                Light Mode
              </motion.span>
            )}
          </AnimatePresence>
        </button>

        {/* Sign Out */}
        <button
          onClick={logout}
          aria-label="Sign out"
          style={{
            background: "transparent",
            border: "none",
            cursor: "pointer",
            color: "var(--status-danger)",
            fontSize: "0.82rem",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            transition: "color 0.25s ease",
            padding: "0.25rem 0",
            display: "flex",
            alignItems: "center",
            gap: "0.35rem",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "#ff6b6b";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "var(--status-danger)";
          }}
        >
          <LogOut size={14} /> Sign Out
        </button>
      </motion.div>
    </nav>
  );
}
