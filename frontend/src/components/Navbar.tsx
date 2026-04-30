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
    <nav className="fixed top-0 left-0 right-0 z-[999] px-12 pt-8 pb-5 pointer-events-none">
      {/* ── Brand — absolute left ── */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] as const }}
        className="absolute left-12 top-8 pointer-events-auto"
      >
        <Link
          href="/"
          className={`font-medium text-lg tracking-tighter no-underline whitespace-nowrap leading-none ${isHomePage ? 'text-white' : 'text-foreground'}`}
        >
          StatementSense
        </Link>
      </motion.div>

      {/* ── Nav Links — true center ── */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] as const }}
        className="w-full flex justify-center gap-8 items-center pointer-events-auto"
      >
        {navLinks.map(({ path, label }) => {
          const active = pathname === path;
          const isHovered = hovered === path;
          const showLine = active || isHovered;

          // Tailwind classes mapped
          const activeClass = isHomePage ? "text-white" : "text-foreground";
          const inactiveClass = isHomePage ? "text-white/60" : "text-muted-foreground";
          const currentClass = active ? activeClass : inactiveClass;

          return (
            <Link
              key={path}
              href={path}
              onMouseEnter={() => setHovered(path)}
              onMouseLeave={() => setHovered(null)}
              className={`relative font-medium no-underline pb-1 text-sm tracking-tight transition-colors duration-250 whitespace-nowrap leading-none ${currentClass}`}
            >
              {label}
              <motion.span
                className={`absolute bottom-0 left-0 right-0 h-[2px] rounded-[1px] origin-center ${activeClass}`}
                style={{ background: 'currentColor' }}
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
        className="absolute right-12 top-8 pointer-events-auto flex gap-4 items-center"
      >
        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          aria-label="Toggle theme"
          className="bg-transparent border-none cursor-pointer text-muted-foreground hover:text-foreground text-sm font-medium tracking-tight transition-colors duration-250 py-1"
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
          className="bg-transparent border-none cursor-pointer text-destructive/80 hover:text-destructive text-sm font-medium tracking-tight transition-colors duration-250 py-1 flex items-center gap-1.5"
        >
          Sign Out <LogOut size={14} />
        </button>
      </motion.div>
    </nav>
  );
}
