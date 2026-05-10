"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { LogOut, Menu, X } from "lucide-react";
import { useTheme } from "./ThemeProvider";
import { useAuth } from "./AuthProvider";

const navLinks = [
  { path: "/subscription", label: "SubscriptionSense" },
  { path: "/renewal", label: "RenewalSense" },
  { path: "/screentime", label: "ScreentimeSense" },
  { path: "/calendar", label: "CalendarSense" },
  { path: "/report", label: "Report" },
];

export default function Navbar() {
  const pathname = usePathname();
  const [hovered, setHovered] = useState<string | null>(null);
  const { theme, toggleTheme } = useTheme();
  const { logout, deleteAccount } = useAuth();
  const isDark = theme === "dark";
  const isHomePage = pathname === "/";
  const navSurfaceClass = isHomePage
    ? ""
    : "bg-background/95 border-b border-border/60 shadow-sm backdrop-blur-md";
  const [mobileOpen, setMobileOpen] = useState(false);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Prevent body scroll when mobile menu is open
  useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileOpen]);

  return (
    <>
      {/* ── Desktop Navbar ── */}
      <nav className={`fixed top-0 left-0 right-0 z-[999] px-12 pt-8 pb-5 pointer-events-none hidden md:block ${navSurfaceClass}`}>
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
            className="bg-transparent border-none cursor-pointer text-muted-foreground hover:text-foreground text-sm font-medium tracking-tight transition-colors duration-250 py-1 flex items-center gap-1.5"
          >
            Sign Out <LogOut size={14} />
          </button>

          {/* Delete Account */}
          <button
            onClick={async () => {
              if (window.confirm("Are you sure you want to delete your account? This action cannot be undone.")) {
                try {
                  await deleteAccount();
                } catch (err: any) {
                  alert(err.message || "Failed to delete account.");
                }
              }
            }}
            className="bg-transparent border-none cursor-pointer text-destructive/40 hover:text-destructive text-[10px] font-medium tracking-tight transition-colors duration-250 py-1"
          >
            Delete Account
          </button>
        </motion.div>
      </nav>

      {/* ── Mobile Navbar ── */}
      <nav className={`fixed top-0 left-0 right-0 z-[999] md:hidden ${navSurfaceClass}`}>
        <div className="flex items-center justify-between px-5 pt-5 pb-4">
          {/* Brand */}
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
          >
            <Link
              href="/"
              className={`font-medium text-lg tracking-tighter no-underline whitespace-nowrap leading-none ${isHomePage ? 'text-white' : 'text-foreground'}`}
            >
              StatementSense
            </Link>
          </motion.div>

          {/* Hamburger Button */}
          <motion.button
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
            className={`bg-transparent border-none cursor-pointer p-1 z-[1001] ${isHomePage && !mobileOpen ? 'text-white' : 'text-foreground'}`}
          >
            <AnimatePresence mode="wait" initial={false}>
              {mobileOpen ? (
                <motion.div
                  key="close"
                  initial={{ opacity: 0, rotate: -90 }}
                  animate={{ opacity: 1, rotate: 0 }}
                  exit={{ opacity: 0, rotate: 90 }}
                  transition={{ duration: 0.2 }}
                >
                  <X size={22} />
                </motion.div>
              ) : (
                <motion.div
                  key="menu"
                  initial={{ opacity: 0, rotate: 90 }}
                  animate={{ opacity: 1, rotate: 0 }}
                  exit={{ opacity: 0, rotate: -90 }}
                  transition={{ duration: 0.2 }}
                >
                  <Menu size={22} />
                </motion.div>
              )}
            </AnimatePresence>
          </motion.button>
        </div>

        {/* ── Mobile Fullscreen Overlay ── */}
        <AnimatePresence>
          {mobileOpen && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3, ease: "easeInOut" }}
              className="fixed inset-0 z-[1000] flex flex-col"
              style={{
                background: isDark
                  ? "rgba(10, 10, 10, 0.97)"
                  : "rgba(255, 255, 255, 0.97)",
                backdropFilter: "blur(20px)",
                WebkitBackdropFilter: "blur(20px)",
              }}
            >
              {/* Spacer for the top bar */}
              <div className="h-16" />

              {/* Nav Links */}
              <div className="flex-1 flex flex-col items-center justify-center gap-1 px-8">
                {navLinks.map(({ path, label }, i) => {
                  const active = pathname === path;
                  return (
                    <motion.div
                      key={path}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 10 }}
                      transition={{
                        duration: 0.35,
                        delay: 0.05 + i * 0.07,
                        ease: [0.25, 0.1, 0.25, 1],
                      }}
                    >
                      <Link
                        href={path}
                        onClick={() => setMobileOpen(false)}
                        className={`block text-center no-underline py-3 text-2xl font-medium tracking-tight transition-colors duration-200 ${
                          active
                            ? "text-foreground"
                            : "text-muted-foreground"
                        }`}
                      >
                        {label}
                      </Link>
                    </motion.div>
                  );
                })}

                {/* Divider */}
                <motion.div
                  initial={{ opacity: 0, scaleX: 0 }}
                  animate={{ opacity: 1, scaleX: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3, delay: 0.25 }}
                  className="w-16 h-px bg-border my-5"
                />

                {/* Theme Toggle */}
                <motion.button
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3, delay: 0.3 }}
                  onClick={toggleTheme}
                  className="bg-transparent border-none cursor-pointer text-muted-foreground text-base font-medium tracking-tight py-2"
                >
                  {isDark ? "Light Mode" : "Dark Mode"}
                </motion.button>

                {/* Sign Out */}
                <motion.button
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3, delay: 0.35 }}
                  onClick={() => {
                    setMobileOpen(false);
                    logout();
                  }}
                  className="bg-transparent border-none cursor-pointer text-muted-foreground text-base font-medium tracking-tight py-2 flex items-center gap-2"
                >
                  Sign Out <LogOut size={16} />
                </motion.button>

                {/* Delete Account */}
                <motion.button
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3, delay: 0.4 }}
                  onClick={async () => {
                    if (window.confirm("Are you sure you want to delete your account? This action cannot be undone.")) {
                      try {
                        setMobileOpen(false);
                        await deleteAccount();
                      } catch (err: any) {
                        alert(err.message || "Failed to delete account.");
                      }
                    }
                  }}
                  className="bg-transparent border-none cursor-pointer text-destructive/50 text-xs font-medium tracking-tight py-2 mt-4"
                >
                  Delete Account
                </motion.button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </nav>
    </>
  );
}
