"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Zap, CheckCircle2, AlertTriangle, RefreshCw, TrendingUp, Code2 } from "lucide-react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId } from "@/store/auth";
import { cn, formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

const HEAL_STATUSES: Record<string, { color: string; label: string }> = {
  healed:       { color: "text-brand-teal",    label: "Auto-Healed"   },
  needs_human:  { color: "text-brand-gold",    label: "Needs Review"  },
  failed:       { color: "text-brand-crimson", label: "Failed"        },
  pending:      { color: "text-content-muted", label: "Pending"       },
};

export default function HealingPage() {
  const orgId = useOrgId();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const { data: statsData } = useQuery({
    queryKey: ["healing-stats", orgId],
    queryFn: () => apiClient.get(`/analytics/${orgId}/healing-roi?days=30`).then(r => r.data),
    enabled: !!orgId,
  });

  const healMutation = useMutation({
    mutationFn: (runId: string) =>
      apiClient.post(`/heal/run`, { run_id: runId, org_id: orgId }),
    onSuccess: () => toast.success("Healing job triggered"),
    onError:   () => toast.error("Healing trigger failed"),
  });

  const stats = statsData || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
            <Zap className="w-7 h-7 text-brand-gold" /> Auto-Healing
          </h1>
          <p className="text-content-muted text-sm mt-1">
            AI-powered selector repair — fix broken tests automatically
          </p>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Auto-Healed (30d)", value: stats.auto_healed_tests ?? "—", color: "text-brand-teal",    icon: CheckCircle2 },
          { label: "Healing Rate",      value: stats.healing_rate_pct != null ? `${stats.healing_rate_pct}%` : "—", color: "text-brand-accent", icon: TrendingUp },
          { label: "Needs Human",       value: stats.tests_needing_human ?? "—", color: "text-brand-gold",   icon: AlertTriangle },
          { label: "Hours Saved",       value: stats.estimated_hours_saved ?? "—", color: "text-brand-cyan",  icon: Zap },
        ].map(({ label, value, color, icon: Icon }, i) => (
          <motion.div key={label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.07 }} className="glass-card p-5">
            <div className="flex items-start gap-3">
              <div className={cn("p-2 rounded-lg bg-current/10 flex-shrink-0", color)}>
                <Icon className={cn("w-5 h-5", color)} />
              </div>
              <div>
                <div className={cn("text-2xl font-black", color)}>{String(value)}</div>
                <div className="text-xs text-content-muted mt-0.5">{label}</div>
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      {/* How it works */}
      <div className="glass-card p-6">
        <h2 className="font-semibold text-content-primary mb-4 flex items-center gap-2">
          <Code2 className="w-5 h-5 text-brand-accent" /> How Auto-Healing Works
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            {
              step: "1",
              title: "Test Fails",
              desc: "A test fails because a CSS selector, XPath, or element attribute changed on your site.",
              color: "border-brand-crimson/30 bg-brand-crimson/5",
            },
            {
              step: "2",
              title: "AI Analyzes",
              desc: "JarviisAI compares the old selector against the current DOM and generates candidate fixes.",
              color: "border-brand-gold/30 bg-brand-gold/5",
            },
            {
              step: "3",
              title: "Auto-Repair",
              desc: "The winning fix is applied, the test is re-run to confirm, and a PR is opened if configured.",
              color: "border-brand-teal/30 bg-brand-teal/5",
            },
          ].map(({ step, title, desc, color }) => (
            <div key={step} className={cn("rounded-xl p-4 border", color)}>
              <div className="w-7 h-7 rounded-full bg-surface-overlay border border-surface-border text-xs font-bold text-content-primary flex items-center justify-center mb-3">
                {step}
              </div>
              <h3 className="font-semibold text-content-primary text-sm mb-1">{title}</h3>
              <p className="text-xs text-content-muted leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Trigger healing */}
      <div className="glass-card p-6">
        <h2 className="font-semibold text-content-primary mb-2 flex items-center gap-2">
          <RefreshCw className="w-4 h-4 text-brand-accent" /> Manual Healing Trigger
        </h2>
        <p className="text-content-muted text-sm mb-4">
          Healing runs automatically after each failed test run. You can also trigger it manually for a specific run ID.
        </p>
        <div className="flex items-center gap-3">
          <input
            value={selectedRunId || ""}
            onChange={e => setSelectedRunId(e.target.value)}
            placeholder="Enter run ID to heal..."
            className="input-field flex-1 font-mono text-sm"
          />
          <motion.button
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            onClick={() => selectedRunId && healMutation.mutate(selectedRunId)}
            disabled={!selectedRunId || healMutation.isPending}
            className="btn-primary flex items-center gap-2 whitespace-nowrap"
          >
            <Zap className="w-4 h-4" />
            {healMutation.isPending ? "Healing..." : "Trigger Healing"}
          </motion.button>
        </div>
        <p className="text-xs text-content-muted mt-2">
          Find run IDs on the <a href="/dashboard/test-runs" className="text-brand-accent hover:underline">Test Runs</a> page
        </p>
      </div>

      {/* ROI summary */}
      <div className="glass-card p-5 border-brand-gold/20 bg-brand-gold/3">
        <div className="flex items-start gap-3">
          <Zap className="w-5 h-5 text-brand-gold mt-0.5 flex-shrink-0" />
          <div>
            <h3 className="font-semibold text-content-primary text-sm mb-1">Healing ROI</h3>
            <p className="text-xs text-content-muted">
              Every auto-healed test saves ~30 minutes of engineering time.
              {stats.auto_healed_tests > 0 && (
                <> With <span className="text-brand-gold font-medium">{stats.auto_healed_tests} healed tests</span>,
                JarviisAI has saved approximately <span className="text-brand-gold font-medium">
                  {Math.round((stats.auto_healed_tests || 0) * 0.5)} hours</span> of manual work.</>
              )}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
