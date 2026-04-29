"use client";

import { useState, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertCircle } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import "./login.css";

/* ── Firebase error → friendly message ── */
function friendlyError(code: string): string {
  const map: Record<string, string> = {
    "auth/invalid-email": "Please enter a valid email address.",
    "auth/user-disabled": "This account has been disabled.",
    "auth/user-not-found": "No account found with this email.",
    "auth/wrong-password": "Incorrect password. Please try again.",
    "auth/invalid-credential": "Invalid email or password.",
    "auth/email-already-in-use": "An account with this email already exists.",
    "auth/weak-password": "Password must be at least 6 characters.",
    "auth/too-many-requests": "Too many attempts. Please wait a moment.",
    "auth/popup-closed-by-user": "Google sign-in was cancelled.",
    "auth/network-request-failed": "Network error. Check your connection.",
  };
  return map[code] || `Something went wrong. (${code || 'Unknown error'})`;
}

/* ── Particle positions (pre-generated) ── */
const PARTICLES = Array.from({ length: 30 }, (_, i) => ({
  id: i,
  left: `${Math.random() * 100}%`,
  size: 1.5 + Math.random() * 2,
  duration: 8 + Math.random() * 12,
  delay: Math.random() * 10,
  opacity: 0.15 + Math.random() * 0.35,
}));

/* ── Google SVG Icon ── */
function GoogleIcon() {
  return (
    <svg className="google-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
        fill="#4285F4"
      />
      <path
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        fill="#34A853"
      />
      <path
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
        fill="#FBBC05"
      />
      <path
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        fill="#EA4335"
      />
    </svg>
  );
}

/* ── Animation variants ── */
const cardVariants = {
  hidden: { opacity: 0, y: 40, scale: 0.96 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.7, ease: [0.25, 0.1, 0.25, 1] as const },
  },
};


const formVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.1 },
  },
  exit: { opacity: 0, transition: { duration: 0.15 } },
};

const fieldVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35 } },
};

const shakeVariants = {
  shake: {
    x: [0, -8, 8, -6, 6, -3, 3, 0],
    transition: { duration: 0.5 },
  },
};

/* ── Branding title character glow ── */
const TITLE = "StatementSense";
const CHAR_DURATION = 0.12;
const SWEEP_TIME = TITLE.length * CHAR_DURATION;

/* ══════════════════════════════════════════════════════════
   Login Page Component
   ══════════════════════════════════════════════════════════ */

export default function LoginPage() {
  const { login, signup, loginWithGoogle } = useAuth();

  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [shakeKey, setShakeKey] = useState(0);

  const clearError = useCallback(() => setError(""), []);

  const triggerError = useCallback((msg: string) => {
    setError(msg);
    setShakeKey((k) => k + 1);
  }, []);

  /* ── Submit handler ── */
  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      clearError();

      if (!email.trim() || !password.trim()) {
        triggerError("Please fill in all fields.");
        return;
      }

      if (mode === "signup" && password !== confirmPassword) {
        triggerError("Passwords do not match.");
        return;
      }

      setLoading(true);
      try {
        if (mode === "login") {
          await login(email, password);
        } else {
          await signup(email, password);
        }
        // AuthProvider handles redirect to /
      } catch (err: unknown) {
        const firebaseErr = err as { code?: string };
        triggerError(friendlyError(firebaseErr.code || ""));
      } finally {
        setLoading(false);
      }
    },
    [email, password, confirmPassword, mode, login, signup, clearError, triggerError]
  );

  /* ── Google handler ── */
  const handleGoogle = useCallback(async () => {
    clearError();
    setGoogleLoading(true);
    try {
      await loginWithGoogle();
    } catch (err: unknown) {
      const firebaseErr = err as { code?: string };
      triggerError(friendlyError(firebaseErr.code || ""));
    } finally {
      setGoogleLoading(false);
    }
  }, [loginWithGoogle, clearError, triggerError]);

  /* ── Tab indicator position ── */
  const tabStyle = useMemo(
    () => ({
      left: mode === "login" ? "4px" : "50%",
      width: "calc(50% - 4px)",
    }),
    [mode]
  );

  return (
    <>
      {/* ── Background layer ── */}
      <div className="login-bg">
        <div className="login-orb-accent" />
        <div className="login-particles">
          {PARTICLES.map((p) => (
            <div
              key={p.id}
              className="login-particle"
              style={{
                left: p.left,
                width: `${p.size}px`,
                height: `${p.size}px`,
                opacity: p.opacity,
                animationDuration: `${p.duration}s`,
                animationDelay: `${p.delay}s`,
              }}
            />
          ))}
        </div>
      </div>

      {/* ── Glass Island ── */}
      <div className="login-page">
        <motion.div
          className="glass-island"
          variants={cardVariants}
          initial="hidden"
          animate="visible"
        >
          {/* ── Brand ── */}
          <div className="login-brand">
            <h1>
              {TITLE.split("").map((char, i) => {
                const delay = i * CHAR_DURATION;
                return (
                  <motion.span
                    key={i}
                    animate={{
                      color: [
                        "rgba(255,255,255,0.35)",
                        "rgba(255,255,255,1)",
                        "rgba(255,255,255,0.35)",
                      ],
                      textShadow: [
                        "0 0 0px rgba(255,255,255,0)",
                        "0 0 14px rgba(255,255,255,0.7), 0 0 35px rgba(255,255,255,0.3)",
                        "0 0 0px rgba(255,255,255,0)",
                      ],
                    }}
                    transition={{
                      duration: 0.8,
                      delay,
                      repeat: Infinity,
                      repeatDelay: SWEEP_TIME - 0.8,
                      ease: "easeInOut",
                    }}
                    style={{ display: "inline-block", whiteSpace: "pre" }}
                  >
                    {char}
                  </motion.span>
                );
              })}
            </h1>
          </div>
          <p className="login-subtitle">Intelligent Subscription Management</p>

          {/* ── Tab Switcher ── */}
          <div className="login-tabs">
            <div className="tab-indicator" style={tabStyle} />
            <button
              type="button"
              className={`login-tab ${mode === "login" ? "active" : ""}`}
              onClick={() => {
                setMode("login");
                clearError();
              }}
            >
              Sign In
            </button>
            <button
              type="button"
              className={`login-tab ${mode === "signup" ? "active" : ""}`}
              onClick={() => {
                setMode("signup");
                clearError();
              }}
            >
              Create Account
            </button>
          </div>

          {/* ── Error ── */}
          <AnimatePresence>
            {error && (
              <motion.div
                key={shakeKey}
                className="login-error"
                initial={{ opacity: 0, height: 0, marginBottom: 0 }}
                animate={{ opacity: 1, height: "auto", marginBottom: 16, ...shakeVariants.shake }}
                exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                transition={{ duration: 0.25 }}
              >
                <AlertCircle size={16} style={{ color: "#f87171", flexShrink: 0 }} />
                <span>{error}</span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ── Form ── */}
          <form onSubmit={handleSubmit}>
            <AnimatePresence mode="wait">
              <motion.div
                key={mode}
                variants={formVariants}
                initial="hidden"
                animate="visible"
                exit="exit"
              >
                <motion.div className="login-input-group" variants={fieldVariants}>
                  <label htmlFor="login-email">Email</label>
                  <input
                    id="login-email"
                    className="login-input"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="email"
                    required
                  />
                </motion.div>

                <motion.div className="login-input-group" variants={fieldVariants}>
                  <label htmlFor="login-password">Password</label>
                  <input
                    id="login-password"
                    className="login-input"
                    type="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    required
                  />
                </motion.div>

                {mode === "signup" && (
                  <motion.div
                    className="login-input-group"
                    variants={fieldVariants}
                    initial="hidden"
                    animate="visible"
                  >
                    <label htmlFor="login-confirm-password">Confirm Password</label>
                    <input
                      id="login-confirm-password"
                      className="login-input"
                      type="password"
                      placeholder="••••••••"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      autoComplete="new-password"
                      required
                    />
                  </motion.div>
                )}

                <motion.div variants={fieldVariants}>
                  <button
                    type="submit"
                    className="login-btn-primary"
                    disabled={loading || googleLoading}
                  >
                    {loading ? (
                      <span className="login-spinner" />
                    ) : mode === "login" ? (
                      "Sign In"
                    ) : (
                      "Create Account"
                    )}
                  </button>
                </motion.div>
              </motion.div>
            </AnimatePresence>
          </form>

          {/* ── Divider ── */}
          <div className="login-divider">
            <span>or</span>
          </div>

          {/* ── Google Button ── */}
          <button
            type="button"
            className="login-btn-google"
            onClick={handleGoogle}
            disabled={loading || googleLoading}
          >
            {googleLoading ? (
              <span className="login-spinner" />
            ) : (
              <>
                <GoogleIcon />
                Continue with Google
              </>
            )}
          </button>
        </motion.div>
      </div>
    </>
  );
}
