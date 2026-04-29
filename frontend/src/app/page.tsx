"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Clock, Calendar as CalendarIcon, Wallet, ArrowRight } from "lucide-react";
import Navbar from "@/components/Navbar";
import MotionCard from "@/components/MotionCard";
import { useTheme } from "@/components/ThemeProvider";

const bgImages = [
  "/apple-music.jpg",
  "/netflix.jpg",
  "/spotify.jpg",
  "/x.jpg",
  "/youtube.jpg",
  "/discord.jpg",
  "/tiktok.jpg",
];

const features = [
  {
    href: "/renewal",
    icon: Wallet,
    imgSrc: "/bankcard.png",
    title: "RenewalSense",
    desc: "Predict subscription renewal failures. Analyze bank statements to map paycycles against recurring charges.",
    gradient: "rgba(18, 18, 18, 0.55)",
  },
  {
    href: "/screentime",
    icon: Clock,
    title: "ScreentimeSense",
    desc: "Catch subscription fatigue early. Track usage trends and optimize spending based on actual engagement.",
    gradient: "rgba(18, 18, 18, 0.55)",
  },
  {
    href: "/calendar",
    icon: CalendarIcon,
    title: "CalendarSense",
    desc: "Pause local subscriptions while traveling. Scan your Google Calendar and match trips to billing cycles.",
    gradient: "rgba(18, 18, 18, 0.55)",
  },
];

const containerVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.12 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.25, 0.1, 0.25, 1] as const } },
};

export default function Home() {
  const [bgIndex, setBgIndex] = useState(0);
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const advanceBg = useCallback(() => {
    setBgIndex((prev) => (prev + 1) % bgImages.length);
  }, []);

  useEffect(() => {
    const delay = 4000;
    const timer = setTimeout(() => {
      advanceBg();
    }, delay);
    return () => clearTimeout(timer);
  }, [bgIndex, advanceBg]);

  return (
    <>
      <Navbar />
      <main style={{ position: "relative", overflow: "hidden", minHeight: "100vh" }}>
        {/* ── Cycling Background Image ── */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 0,
            pointerEvents: "none",
            backgroundColor: "#000",
          }}
        >
          <AnimatePresence>
            <motion.img
              key={bgImages[bgIndex]}
              src={bgImages[bgIndex]}
              alt=""
              initial={{ opacity: 0 }}
              animate={{ opacity: isDark ? 0.4 : 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 2, ease: "easeInOut" }}
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                objectFit: "cover",
                filter: "blur(3px)",
              }}
            />
          </AnimatePresence>
          {/* Subtle vignette — no heavy color wash */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: isDark
                ? "radial-gradient(ellipse at center, transparent 40%, var(--bg-primary) 100%)"
                : "none",
            }}
          />
        </div>

        {/* ── Foreground Content ── */}
        <div className="container" style={{ position: "relative", zIndex: 10, paddingTop: "8rem", paddingBottom: "4.8rem" }}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.25, 0.1, 0.25, 1] as const }}
          style={{ textAlign: "center", maxWidth: "640px", margin: "0 auto 6.5rem" }}
        >
          <h1
            style={{
              fontSize: "3.2rem",
              fontWeight: 700,
              letterSpacing: "-0.05em",
              lineHeight: 1.15,
              marginBottom: "1.25rem",
              color: "#ffffff",
              textShadow: "0 0 20px rgba(255, 255, 255, 0.35), 0 0 60px rgba(255, 255, 255, 0.15)",
            }}
          >
            Intelligent Subscription Management.
          </h1>
          <p
            style={{
              fontSize: "1.1rem",
              color: "rgba(255, 255, 255, 0.85)",
              lineHeight: 1.6,
            }}
          >
            StatementSense helps users save money by monitoring their
            subscriptions and how much they actually use them.
          </p>
        </motion.div>

        {/* Feature Cards */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="show"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "1.25rem",
            maxWidth: "1040px",
            margin: "0 auto",
            padding: "1rem",
            borderRadius: "20px",
            background: "rgba(10, 10, 10, 0.3)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          {features.map(({ href, icon: Icon, imgSrc, title, desc, gradient }, cardIndex) => {
            // Calculate character offset with gap between cards
            const cardGap = 8; // virtual chars of spacing between cards
            const charOffset = features
              .slice(0, cardIndex)
              .reduce((sum, f) => sum + f.title.length + cardGap, 0);
            const totalChars = features.reduce((sum, f) => sum + f.title.length, 0) + cardGap * (features.length - 1);
            const charDuration = 0.12; // seconds per character stagger
            const sweepTime = totalChars * charDuration;
            const cycleDuration = sweepTime; // no pause, restart immediately

            return (
            <motion.div key={href} variants={itemVariants}>
              <Link href={href} style={{ textDecoration: "none", color: "inherit" }}>
                <MotionCard
                  hover
                  style={{
                    height: "100%",
                    background: gradient,
                    backdropFilter: "blur(12px)",
                    WebkitBackdropFilter: "blur(12px)",
                    border: "1px solid rgba(255, 255, 255, 0.06)",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
                    <h2
                      style={{
                        fontSize: "1.15rem",
                        fontWeight: 700,
                        marginBottom: "0.5rem",
                        letterSpacing: "-0.01em",
                        display: "flex",
                      }}
                    >
                      {title.split("").map((char, i) => {
                        const globalIndex = charOffset + i;
                        const delay = globalIndex * charDuration;
                        return (
                          <motion.span
                            key={i}
                            animate={{
                              color: [
                                "rgba(255,255,255,0.4)",
                                "rgba(255,255,255,1)",
                                "rgba(255,255,255,0.4)",
                              ],
                              textShadow: [
                                "0 0 0px rgba(255,255,255,0)",
                                "0 0 12px rgba(255,255,255,0.7), 0 0 30px rgba(255,255,255,0.3)",
                                "0 0 0px rgba(255,255,255,0)",
                              ],
                            }}
                            transition={{
                              duration: 0.8,
                              delay,
                              repeat: Infinity,
                              repeatDelay: cycleDuration - 0.8,
                              ease: "easeInOut",
                            }}
                            style={{ display: "inline-block", whiteSpace: "pre" }}
                          >
                            {char}
                          </motion.span>
                        );
                      })}
                    </h2>
                    <p
                      style={{
                        fontSize: "0.88rem",
                        color: "rgba(255, 255, 255, 0.7)",
                        lineHeight: 1.55,
                        marginBottom: "1.5rem",
                        flexGrow: 1,
                      }}
                    >
                      {desc}
                    </p>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.35rem",
                        color: "var(--accent-teal)",
                        fontWeight: 600,
                        fontSize: "0.88rem",
                      }}
                    >
                      Get Started <ArrowRight size={15} />
                    </div>
                  </div>
                </MotionCard>
              </Link>
            </motion.div>
            );
          })}
        </motion.div>
        </div>
      </main>
    </>
  );
}
