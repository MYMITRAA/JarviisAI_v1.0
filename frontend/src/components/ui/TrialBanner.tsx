"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Zap, ArrowRight, X } from "lucide-react";
import { useState, useEffect } from "react";
import { useAuthStore, useTrialActive, useTrialHours } from "@/store/auth";
import Link from "next/link";
import { cn } from "@/lib/utils";

export function TrialBanner() {
  const [dismissed, setDismissed] = useState(false);
  const [timeLeft, setTimeLeft] = useState({ hours: 0, minutes: 0 });

  const trialActive = useTrialActive();
  const trialHoursRemaining = useTrialHours();

  useEffect(() => {
    if (!trialActive) return;
    const update = () => {
      const h = Math.floor(trialHoursRemaining);
      const m = Math.floor((trialHoursRemaining - h) * 60);
      setTimeLeft({ hours: h, minutes: m });
    };
    update();
    const interval = setInterval(update, 60_000);
    return () => clearInterval(interval);
  }, [trialActive, trialHoursRemaining]);

  if (!trialActive || dismissed) return null;

  const isUrgent = trialHoursRemaining < 12;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ height: 0, opacity: 0 }}
        animate={{ height: "auto", opacity: 1 }}
        exit={{ height: 0, opacity: 0 }}
        className={cn(
          "border-b px-4 py-2.5",
          isUrgent
            ? "bg-brand-crimson/10 border-brand-crimson/30"
            : "bg-brand-accent/10 border-brand-accent/30"
        )}
      >
        <div className="flex items-center justify-between max-w-6xl mx-auto">
          <div className="flex items-center gap-3">
            <Zap className={cn("w-4 h-4 flex-shrink-0", isUrgent ? "text-brand-crimson" : "text-brand-accent")} />
            <p className={cn("text-sm font-medium", isUrgent ? "text-brand-crimson" : "text-brand-accent")}>
              {isUrgent
                ? `⏰ Your free trial expires in ${timeLeft.hours}h ${timeLeft.minutes}m — don't lose access!`
                : `🚀 You're on a 2-day Pro trial — ${timeLeft.hours}h ${timeLeft.minutes}m remaining`
              }
            </p>
            <span className="text-xs text-content-muted hidden sm:inline">
              Full Pro features unlocked: AI testing, Deploy engine, API testing
            </span>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Link href="/settings/billing">
              <motion.button
                whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
                  isUrgent
                    ? "bg-brand-crimson text-white hover:bg-brand-crimson/80"
                    : "bg-brand-accent text-white hover:bg-brand-accent/80"
                )}
              >
                Upgrade Now <ArrowRight className="w-3 h-3" />
              </motion.button>
            </Link>
            <button
              onClick={() => setDismissed(true)}
              className="text-content-muted hover:text-content-primary transition-colors p-1"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
