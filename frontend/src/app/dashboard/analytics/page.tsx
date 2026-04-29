"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { BarChart3, TrendingUp, TrendingDown, Rocket, Activity, Zap, RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { apiClient } from "@/lib/api";
import { useOrgId } from "@/store/auth";
import { cn } from "@/lib/utils";

const PERIOD_OPTIONS = [
  { label: "7 days",  value: 7  },
  { label: "30 days", value: 30 },
  { label: "90 days", value: 90 },
];

function StatCard({ title, value, subtitle, icon: Icon, color }: {
  title: string; value: string | number;
  subtitle?: string; icon: any; color: string;
}) {
  return (
    <motion.div whileHover={{ y: -2 }} className="glass-card p-5">
      <div className={cn("p-2 rounded-lg w-fit mb-3", `bg-${color}/10 border border-${color}/20`)}>
        <Icon className={cn("w-5 h-5", `text-${color}`)} />
      </div>
      <div className="text-2xl font-black text-content-primary mb-0.5">{value ?? "—"}</div>
      <div className="text-sm text-content-muted">{title}</div>
      {subtitle && <div className="text-xs text-content-muted mt-0.5">{subtitle}</div>}
    </motion.div>
  );
}

const ChartTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-surface-raised border border-surface-border rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-content-muted mb-1">{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: <span className="font-bold">{p.value?.toFixed?.(1) ?? p.value}</span>
          {p.name === "Pass Rate" ? "%" : ""}
        </p>
      ))}
    </div>
  );
};

export default function AnalyticsPage() {
  const orgId = useOrgId();
  const [period, setPeriod] = useState(30);

  const { data: overview, isLoading, refetch } = useQuery({
    queryKey: ["analytics-overview", orgId, period],
    queryFn: () => apiClient.get(`/analytics/${orgId}/overview?days=${period}`).then(r => r.data),
    enabled: !!orgId,
    refetchInterval: 60_000,
  });

  const { data: trendRaw } = useQuery({
    queryKey: ["analytics-trend", orgId, period],
    queryFn: () => apiClient.get(`/analytics/${orgId}/pass-rate-trend?days=${Math.min(period, 30)}`).then(r => r.data),
    enabled: !!orgId,
    refetchInterval: 120_000,
  });

  const reliability  = overview?.reliability  || {};
  const deployments  = overview?.deployments  || {};
  const healing      = overview?.healing      || {};

  // Build trend chart data from real API data
  const trendData = (trendRaw || []).map((d: any) => ({
    date: new Date(d.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    "Pass Rate": d.pass_rate,
    "Runs": d.runs,
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
            <BarChart3 className="w-7 h-7 text-brand-accent" /> Analytics
          </h1>
          <p className="text-content-muted text-sm mt-1">Platform-wide trends and quality metrics</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1 p-1 bg-surface-overlay border border-surface-border rounded-lg">
            {PERIOD_OPTIONS.map(opt => (
              <button key={opt.value} onClick={() => setPeriod(opt.value)}
                className={cn("px-3 py-1.5 rounded text-xs font-medium transition-all",
                  period === opt.value
                    ? "bg-brand-accent/15 text-brand-accent border border-brand-accent/25"
                    : "text-content-muted hover:text-content-primary")}>
                {opt.label}
              </button>
            ))}
          </div>
          <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
            onClick={() => refetch()}
            className="p-2 border border-surface-border rounded-lg hover:border-brand-accent/40 text-content-muted hover:text-brand-accent transition-all">
            <RefreshCw className="w-4 h-4" />
          </motion.button>
        </div>
      </div>

      {/* Stats */}
      {isLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => (
            <div key={i} className="glass-card p-5 animate-pulse">
              <div className="h-9 w-9 bg-surface-border rounded-lg mb-3" />
              <div className="h-7 bg-surface-border rounded mb-1 w-16" />
              <div className="h-3 bg-surface-border rounded w-2/3" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={Activity}  color="brand-teal"   title="Pass Rate"      value={reliability.pass_rate    != null ? `${reliability.pass_rate}%`    : "—"} subtitle={`${reliability.total_runs ?? 0} runs`} />
          <StatCard icon={BarChart3} color="brand-accent"  title="Total Runs"    value={reliability.total_runs   ?? 0}  subtitle={`${reliability.failed_runs ?? 0} failed`} />
          <StatCard icon={Rocket}    color="brand-cyan"    title="Deployments"   value={deployments.total_deployments ?? 0} subtitle={deployments.rollback_rate != null ? `${deployments.rollback_rate}% rollback rate` : undefined} />
          <StatCard icon={Zap}       color="brand-gold"    title="Auto-Healed"   value={healing.auto_healed_tests ?? 0} subtitle={healing.healing_rate_pct != null ? `${healing.healing_rate_pct}% success` : undefined} />
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-card p-5">
          <h2 className="font-semibold text-content-primary mb-4 flex items-center gap-2">
            <Activity className="w-4 h-4 text-brand-teal" /> Pass Rate Trend
          </h2>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={trendData}>
              <defs>
                <linearGradient id="passGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f1f3e" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#6b7280" }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#6b7280" }} unit="%" />
              <Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey="Pass Rate" stroke="#10b981" fill="url(#passGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="glass-card p-5">
          <h2 className="font-semibold text-content-primary mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-brand-accent" /> Daily Runs
          </h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f1f3e" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#6b7280" }} />
              <YAxis tick={{ fontSize: 10, fill: "#6b7280" }} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="Runs" fill="#6d28d9" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Detail tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-card p-5">
          <h2 className="font-semibold text-content-primary mb-4 flex items-center gap-2">
            <Activity className="w-4 h-4 text-brand-teal" /> Test Reliability
          </h2>
          {[
            ["Total Runs",  reliability.total_runs  ?? "—"],
            ["Passed",      reliability.passed_runs ?? "—"],
            ["Failed",      reliability.failed_runs ?? "—"],
            ["Pass Rate",   reliability.pass_rate != null ? `${reliability.pass_rate}%` : "—"],
          ].map(([label, val]) => (
            <div key={String(label)} className="flex justify-between py-2.5 border-b border-surface-border last:border-0">
              <span className="text-sm text-content-secondary">{label}</span>
              <span className="text-sm font-semibold font-mono text-content-primary">{String(val)}</span>
            </div>
          ))}
        </div>

        <div className="glass-card p-5">
          <h2 className="font-semibold text-content-primary mb-4 flex items-center gap-2">
            <Rocket className="w-4 h-4 text-brand-cyan" /> Deployments
          </h2>
          {[
            ["Total",        deployments.total_deployments ?? "—"],
            ["Successful",   deployments.successful ?? "—"],
            ["Rollbacks",    deployments.rollbacks ?? "—"],
            ["Rollback Rate",deployments.rollback_rate != null ? `${deployments.rollback_rate}%` : "—"],
            ["Avg Time",     deployments.avg_deploy_seconds ? `${deployments.avg_deploy_seconds}s` : "—"],
          ].map(([label, val]) => (
            <div key={String(label)} className="flex justify-between py-2.5 border-b border-surface-border last:border-0">
              <span className="text-sm text-content-secondary">{label}</span>
              <span className="text-sm font-semibold font-mono text-content-primary">{String(val)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Healing ROI */}
      <div className="glass-card p-5">
        <h2 className="font-semibold text-content-primary mb-4 flex items-center gap-2">
          <Zap className="w-4 h-4 text-brand-gold" /> Auto-Healing ROI
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            ["Auto-Healed",   healing.auto_healed_tests ?? "—"],
            ["Heal Rate",     healing.healing_rate_pct != null ? `${healing.healing_rate_pct}%` : "—"],
            ["Hours Saved",   healing.estimated_hours_saved ?? "—"],
            ["Cost Saved",    healing.estimated_cost_saved ? `$${healing.estimated_cost_saved}` : "—"],
          ].map(([label, val]) => (
            <div key={String(label)} className="bg-surface-overlay rounded-lg p-4 text-center border border-surface-border">
              <div className="text-xl font-black text-brand-gold mb-1">{String(val)}</div>
              <div className="text-xs text-content-muted">{label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
