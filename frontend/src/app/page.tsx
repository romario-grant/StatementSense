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
  },
  {
    href: "/screentime",
    icon: Clock,
    title: "ScreentimeSense",
    desc: "Catch subscription fatigue early. Track usage trends and optimize spending based on actual engagement.",
  },
  {
    href: "/calendar",
    icon: CalendarIcon,
    title: "CalendarSense",
    desc: "Pause local subscriptions while traveling. Scan your Google Calendar and match trips to billing cycles.",
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
      <main className="relative overflow-hidden min-h-screen">
        {/* ── Cycling Background Image ── */}
        <div className="absolute inset-0 z-0 pointer-events-none bg-black">
          <AnimatePresence>
            <motion.img
              key={bgImages[bgIndex]}
              src={bgImages[bgIndex]}
              alt=""
              initial={{ opacity: 0 }}
              animate={{ opacity: isDark ? 0.4 : 0.8 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 2, ease: "easeInOut" }}
              className="absolute inset-0 w-full h-full object-cover blur-[3px]"
            />
          </AnimatePresence>
          {/* Subtle vignette */}
          <div className={`absolute inset-0 ${isDark ? 'bg-[radial-gradient(ellipse_at_center,transparent_40%,hsl(var(--background))_100%)]' : ''}`} />
        </div>

        {/* ── Foreground Content ── */}
        <div className="relative z-10 pt-32 pb-20 max-w-6xl mx-auto px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.25, 0.1, 0.25, 1] as const }}
            className="text-center max-w-2xl mx-auto mb-24"
          >
            <h1 className="text-5xl font-bold tracking-tight leading-[1.15] mb-5 text-white drop-shadow-[0_0_20px_rgba(255,255,255,0.35)]">
              Intelligent Subscription Management.
            </h1>
            <p className="text-lg text-white/85 leading-relaxed">
              StatementSense helps users save money by monitoring their
              subscriptions and how much they actually use them.
            </p>
          </motion.div>

          {/* Feature Cards */}
          <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="show"
            className="grid grid-cols-1 md:grid-cols-3 gap-5 max-w-5xl mx-auto p-4 rounded-[20px] bg-black/30 border border-white/10 backdrop-blur-md"
          >
            {features.map(({ href, icon: Icon, title, desc }, cardIndex) => {
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
                <Link href={href} className="no-underline text-inherit block h-full">
                  <MotionCard
                    hover
                    className="h-full bg-white/5 dark:bg-black/55 backdrop-blur-xl border border-white/10 cursor-pointer p-6"
                  >
                    <div className="flex flex-col h-full">
                      <h2 className="text-lg font-bold mb-2 tracking-tight flex text-white">
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
                              className="inline-block whitespace-pre"
                            >
                              {char}
                            </motion.span>
                          );
                        })}
                      </h2>
                      <p className="text-sm text-white/70 leading-relaxed mb-6 flex-grow">
                        {desc}
                      </p>
                      <div className="flex items-center gap-1.5 text-cyan-500 font-semibold text-sm">
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
