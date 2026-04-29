"use client";

import { motion } from "framer-motion";
import { Zap, ArrowRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId, usePlan } from "@/store/auth";
import { cn } from "@/lib/utils";
import Link from "next/link";

interface UsageBarProps {
  metric: string;
  label: string;
  current: number;
  limit: number;
  unlimited: boolean;
  percentage: number;
  warning: boolean;
  over: boolean;
}

function UsageBar({ metric, label, current, limit, unlimited, percentage, warning, over }: UsageBarProps) {
  const color = over ? "bg-brand-crimson" : warning ? "bg-brand-gold" : "bg-brand-accent";
  const textColor = over ? "text-brand-crimson" : warning ? "text-brand-gold" : "text-content-muted";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-content-secondary font-medium capitalize">{label.replace(/_/g, " ")}</span>
        <span className={cn("font-mono", textColor)}>
          {unlimited ? "∞ Unlimited" : `${current} / ${limit}`}
        </span>
      </div>
      {!unlimited && (
        <div className="h-1.5 bg-surface-border rounded-full overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(100, percentage)}%` }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            className={cn("h-full rounded-full", color)}
          />
        </div>
      )}
      {warning && !over && (
        <p className="text-xs text-brand-gold">⚠ {percentage.toFixed(0)}% used — consider upgrading</p>
      )}
      {over && (
        <p className="text-xs text-brand-crimson">🚫 Limit reached — upgrade to continue</p>
      )}
    </div>
  );
}

const METRIC_LABELS: Record<string, string> = {
  test_runs: "Test Runs / month",
  deployments: "Deployments / month",
  ai_generations: "AI Generations / month",
  security_scans: "Security Scans / month",
  projects: "Projects (total)",
  team_members: "Team Members (total)",
};

export function UsageIndicator({ compact = false }: { compact?: boolean }) {
  const orgId = useOrgId();
  const plan = usePlan();

  const { data: usage, isLoading } = useQuery({
    queryKey: ["usage", orgId, plan],
    queryFn: () => apiClient.get(`/usage/${orgId}?plan=${plan}`).then(r => r.data),
    enabled: !!orgId,
    refetchInterval: 60_000,
  });

  if (isLoading || !usage) {
    return compact ? null : (
      <div className="glass-card p-5 animate-pulse">
        <div className="h-4 bg-surface-border rounded w-1/3 mb-3" />
        <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="h-3 bg-surface-border rounded" />)}</div>
      </div>
    );
  }

  const metrics = Object.entries(usage).filter(([k]) => !k.startsWith("_")) as [string, any][];
  const hasWarning = metrics.some(([, v]) => v.warning);
  const hasOver = metrics.some(([, v]) => v.over);

  if (compact) {
    // Compact mode: just show a single bar for test_runs
    const runs = usage.test_runs;
    if (!runs || runs.unlimited) return null;
    return (
      <div className="px-3 py-2 border-t border-surface-border">
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-content-muted">Test runs</span>
          <span className={cn("font-mono", runs.over ? "text-brand-crimson" : runs.warning ? "text-brand-gold" : "text-content-muted")}>
            {runs.current}/{runs.limit}
          </span>
        </div>
        <div className="h-1 bg-surface-border rounded-full overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all", runs.over ? "bg-brand-crimson" : runs.warning ? "bg-brand-gold" : "bg-brand-accent")}
            style={{ width: `${Math.min(100, runs.percentage)}%` }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-content-primary flex items-center gap-2">
          <Zap className="w-4 h-4 text-brand-accent" />
          Usage — <span className="capitalize text-brand-accent">{plan}</span> plan
        </h2>
        {(hasWarning || hasOver) && (
          <Link href="/settings/billing">
            <button className="text-xs text-brand-accent hover:text-brand-cyan transition-colors flex items-center gap-1">
              Upgrade <ArrowRight className="w-3 h-3" />
            </button>
          </Link>
        )}
      </div>

      <div className="space-y-4">
        {metrics.map(([key, val]) => (
          <UsageBar
            key={key}
            metric={key}
            label={METRIC_LABELS[key] || key}
            current={val.current}
            limit={val.limit}
            unlimited={val.unlimited}
            percentage={val.percentage}
            warning={val.warning}
            over={val.over}
          />
        ))}
      </div>

      {usage._period && (
        <p className="text-xs text-content-muted border-t border-surface-border pt-3">
          Billing period: {usage._period} · <Link href="/settings/billing" className="text-brand-accent hover:underline">Manage plan</Link>
        </p>
      )}
    </div>
  );
}
