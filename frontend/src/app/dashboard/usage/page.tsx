"use client";

import { motion } from "framer-motion";
import { BarChart3, ArrowRight, Zap, RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId, usePlan, useAuthStore, useTrialActive, useTrialHours } from "@/store/auth";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { UsageIndicator } from "@/components/ui/UsageIndicator";

const PLAN_LIMITS: Record<string, Record<string, number | string>> = {
  free:       { test_runs: 100,   projects: 3,   team_members: 1,  deployments: 10,  ai_generations: 20 },
  starter:    { test_runs: 100,   projects: 3,   team_members: 1,  deployments: 10,  ai_generations: 20 },
  pro:        { test_runs: 2000,  projects: 20,  team_members: 5,  deployments: 200, ai_generations: 500 },
  team:       { test_runs: 10000, projects: 100, team_members: 25, deployments: 1000,ai_generations: 2000 },
  enterprise: { test_runs: "∞",   projects: "∞", team_members: "∞",deployments: "∞", ai_generations: "∞" },
};

const UPGRADE_BENEFITS: Record<string, string[]> = {
  free:    ["Pro: 2,000 test runs/mo", "API Testing", "Deploy Engine", "Self-Healing", "5 team members"],
  starter: ["Pro: 2,000 test runs/mo", "API Testing", "Deploy Engine", "Self-Healing", "5 team members"],
  pro:     ["Team: 10,000 test runs/mo", "COBOL Testing", "25 team members", "Jarviis AI Assistant"],
  team:    ["Enterprise: Unlimited everything", "SAML SSO", "Compliance exports", "Dedicated support"],
};

export default function UsagePage() {
  const orgId = useOrgId();
  const plan = usePlan();
  const trialActive = useTrialActive();
  const trialHours = useTrialHours();

  const { data: usage, isLoading, refetch } = useQuery({
    queryKey: ["usage-full", orgId, plan],
    queryFn: () => apiClient.get(`/usage/${orgId}?plan=${plan}`).then(r => r.data),
    enabled: !!orgId,
    refetchInterval: 30_000,
  });

  const METRIC_LABELS: Record<string, string> = {
    test_runs:      "Test Runs / month",
    deployments:    "Deployments / month",
    ai_generations: "AI Generations / month",
    security_scans: "Security Scans / month",
    projects:       "Projects (total)",
    team_members:   "Team Members (total)",
  };

  const currentLimits = PLAN_LIMITS[plan] || PLAN_LIMITS.free;
  const benefits = UPGRADE_BENEFITS[plan];
  const canUpgrade = plan !== "enterprise";

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
            <BarChart3 className="w-6 h-6 text-brand-accent" />
            Usage
          </h1>
          <p className="text-content-muted text-sm mt-1">
            Monitor your plan usage and limits
          </p>
        </div>
        <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
          onClick={() => refetch()}
          className="p-2 border border-surface-border rounded-lg hover:border-brand-accent/40 transition-all text-content-muted hover:text-brand-accent">
          <RefreshCw className="w-4 h-4" />
        </motion.button>
      </div>

      {/* Trial banner */}
      {trialActive && (
        <div className="glass-card p-4 border-brand-accent/30 bg-brand-accent/5">
          <div className="flex items-center gap-3">
            <Zap className="w-5 h-5 text-brand-accent flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-brand-accent">2-Day Pro Trial Active</p>
              <p className="text-xs text-content-muted mt-0.5">
                {trialHours > 0 ? `${Math.floor(trialHours)}h ${Math.floor((trialHours % 1) * 60)}m remaining` : "Trial ending soon"} ·
                You have full Pro features during your trial
              </p>
            </div>
            <Link href="/settings/billing">
              <button className="text-xs text-brand-accent hover:text-brand-cyan transition-colors flex items-center gap-1">
                Upgrade <ArrowRight className="w-3 h-3" />
              </button>
            </Link>
          </div>
        </div>
      )}

      {/* Plan info */}
      <div className="glass-card p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-xs text-content-muted uppercase tracking-wider">Current Plan</p>
            <p className="text-xl font-black text-brand-accent capitalize mt-0.5">{plan}</p>
          </div>
          {canUpgrade && (
            <Link href="/settings/billing">
              <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                className="flex items-center gap-2 px-4 py-2 bg-brand-accent text-white rounded-lg text-sm font-semibold hover:bg-brand-accent/80 transition-all">
                Upgrade Plan <ArrowRight className="w-4 h-4" />
              </motion.button>
            </Link>
          )}
        </div>

        {/* Period */}
        {usage?._period && (
          <p className="text-xs text-content-muted mb-4">
            Billing period: <span className="text-content-secondary font-medium">{usage._period}</span> ·
            Resets on the 1st of each month
          </p>
        )}

        {/* Usage bars */}
        {isLoading ? (
          <div className="space-y-4">
            {[1,2,3,4].map(i => (
              <div key={i} className="space-y-1.5">
                <div className="flex justify-between">
                  <div className="h-3 bg-surface-border rounded w-32 animate-pulse" />
                  <div className="h-3 bg-surface-border rounded w-16 animate-pulse" />
                </div>
                <div className="h-1.5 bg-surface-border rounded animate-pulse" />
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-5">
            {usage && Object.entries(usage)
              .filter(([k]) => !k.startsWith("_"))
              .map(([key, val]: [string, any]) => {
                const pct = Math.min(100, val.percentage || 0);
                const barColor = val.over ? "bg-brand-crimson" : val.warning ? "bg-brand-gold" : "bg-brand-accent";
                const textColor = val.over ? "text-brand-crimson" : val.warning ? "text-brand-gold" : "text-content-muted";

                return (
                  <div key={key} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-content-secondary font-medium">
                        {METRIC_LABELS[key] || key.replace(/_/g, " ")}
                      </span>
                      <span className={cn("font-mono", textColor)}>
                        {val.unlimited ? "Unlimited" : `${val.current ?? 0} / ${val.limit}`}
                        {val.warning && !val.over && " ⚠"}
                        {val.over && " 🚫"}
                      </span>
                    </div>
                    {!val.unlimited && (
                      <div className="h-2 bg-surface-border rounded-full overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${pct}%` }}
                          transition={{ duration: 0.7, ease: "easeOut" }}
                          className={cn("h-full rounded-full", barColor)}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
        )}
      </div>

      {/* Upgrade benefits */}
      {canUpgrade && benefits && (
        <div className="glass-card p-5">
          <h2 className="font-semibold text-content-primary mb-3 flex items-center gap-2">
            <Zap className="w-4 h-4 text-brand-accent" />
            What you get by upgrading
          </h2>
          <ul className="space-y-2 mb-4">
            {benefits.map(b => (
              <li key={b} className="flex items-center gap-2 text-sm text-content-secondary">
                <div className="w-1.5 h-1.5 bg-brand-teal rounded-full flex-shrink-0" />
                {b}
              </li>
            ))}
          </ul>
          <Link href="/settings/billing">
            <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
              className="w-full py-2.5 bg-brand-accent/15 text-brand-accent border border-brand-accent/30 rounded-lg text-sm font-semibold hover:bg-brand-accent/25 transition-all flex items-center justify-center gap-2">
              View Upgrade Options <ArrowRight className="w-4 h-4" />
            </motion.button>
          </Link>
        </div>
      )}
    </div>
  );
}
