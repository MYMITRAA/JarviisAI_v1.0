"use client";

import { motion } from "framer-motion";
import {
  Play, CheckCircle2, XCircle, Clock, Rocket,
  Zap, TrendingUp, Activity, Shield, GitBranch, ArrowRight
} from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId } from "@/store/auth";
import { cn, formatRelativeTime } from "@/lib/utils";

// ── Stat card ──────────────────────────────────────────────────
function StatCard({
  label, value, delta, icon: Icon, color, href, loading
}: {
  label: string; value: string | number; delta?: string;
  icon: any; color: string; href?: string; loading?: boolean;
}) {
  const content = (
    <motion.div
      whileHover={{ y: -2, scale: 1.01 }}
      className="glass-card p-5 cursor-pointer glow-border group"
    >
      <div className="flex items-start justify-between mb-3">
        <div className={cn("p-2 rounded-lg", `bg-${color}/10 border border-${color}/20`)}>
          <Icon className={cn("w-5 h-5", `text-${color}`)} />
        </div>
        {delta && (
          <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full",
            delta.startsWith("+") ? "text-brand-teal bg-brand-teal/10" : "text-brand-crimson bg-brand-crimson/10"
          )}>
            {delta}
          </span>
        )}
      </div>
      {loading ? (
        <div className="h-8 bg-surface-border rounded animate-pulse mb-1" />
      ) : (
        <div className="text-2xl font-black text-content-primary mb-0.5">{value}</div>
      )}
      <div className="text-sm text-content-muted">{label}</div>
    </motion.div>
  );
  return href ? <Link href={href}>{content}</Link> : content;
}

// ── Activity item ──────────────────────────────────────────────
function ActivityItem({ type, title, time, status }: {
  type: "test" | "deploy" | "heal"; title: string; time: string; status: "pass" | "fail" | "running";
}) {
  const icons = { test: Play, deploy: Rocket, heal: Activity };
  const Icon = icons[type];
  const statusColors = {
    pass: "text-brand-teal", fail: "text-brand-crimson", running: "text-brand-accent"
  };
  const statusIcons = {
    pass: CheckCircle2, fail: XCircle, running: Clock
  };
  const StatusIcon = statusIcons[status];

  return (
    <div className="flex items-center gap-3 py-3 border-b border-surface-border last:border-0">
      <div className="w-8 h-8 rounded-lg bg-surface-overlay border border-surface-border flex items-center justify-center flex-shrink-0">
        <Icon className="w-4 h-4 text-content-muted" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-content-primary truncate">{title}</p>
        <p className="text-xs text-content-muted">{time}</p>
      </div>
      <StatusIcon className={cn("w-4 h-4 flex-shrink-0", statusColors[status])} />
    </div>
  );
}

// ── AI recommendation ──────────────────────────────────────────
function AIRecommendation({ text, action, href }: { text: string; action: string; href: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-start gap-3 p-3 bg-brand-accent/5 border border-brand-accent/20 rounded-lg"
    >
      <Zap className="w-4 h-4 text-brand-accent mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-content-primary">{text}</p>
      </div>
      <Link href={href}>
        <button className="text-xs text-brand-accent hover:text-brand-cyan font-medium whitespace-nowrap flex items-center gap-1 transition-colors">
          {action} <ArrowRight className="w-3 h-3" />
        </button>
      </Link>
    </motion.div>
  );
}

// ── Main dashboard ─────────────────────────────────────────────
export default function DashboardPage() {
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const greeting = new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening";

  // Fetch real org stats
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["org-stats", orgId],
    queryFn: () => apiClient.get(`/orgs/${orgId}/stats`).then(r => r.data),
    enabled: !!orgId,
    refetchInterval: 30_000,
  });

  // Fetch recent runs for activity feed
  const { data: recentData } = useQuery({
    queryKey: ["recent-runs", orgId],
    queryFn: () => apiClient.get(`/orgs/${orgId}/projects`).then(r => r.data),
    enabled: !!orgId,
    refetchInterval: 30_000,
  });

  const hasProjects = (recentData?.total ?? 0) > 0;

  const statCards = [
    {
      label: "Tests Run Today",
      value: statsLoading ? "…" : (stats?.tests_run_today ?? 0),
      icon: Play, color: "brand-accent", href: "/dashboard/test-runs",
    },
    {
      label: "Pass Rate Today",
      value: statsLoading ? "…" : stats?.pass_rate_today != null ? `${stats.pass_rate_today}%` : "—",
      icon: CheckCircle2, color: "brand-teal", href: "/dashboard/test-runs",
    },
    {
      label: "Active Runs",
      value: statsLoading ? "…" : (stats?.active_runs ?? 0),
      icon: Activity, color: "brand-cyan", href: "/dashboard/test-runs",
    },
    {
      label: "Total Projects",
      value: statsLoading ? "…" : (stats?.total_projects ?? 0),
      icon: Shield, color: "brand-gold", href: "/projects",
    },
  ];

  const aiRecommendations = hasProjects ? [
    {
      text: `${stats?.failed_runs_today ?? 0} test run${(stats?.failed_runs_today ?? 0) !== 1 ? "s" : ""} failed today — review failures and trigger auto-healing`,
      action: "View Failures",
      href: "/dashboard/test-runs",
    },
    {
      text: "Connect GitHub to enable automatic test runs on every push and pull request",
      action: "Connect GitHub",
      href: "/settings/integrations",
    },
  ] : [
    {
      text: "Create your first project to start autonomous testing",
      action: "Create Project",
      href: "/projects/new",
    },
    {
      text: "Connect your GitHub repository to enable CI/CD triggers",
      action: "Connect GitHub",
      href: "/settings/integrations",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Welcome header */}
      <div className="flex items-start justify-between">
        <div>
          <motion.h1
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-2xl font-black text-content-primary"
          >
            {greeting},{" "}
            <span className="text-gradient">{user?.full_name?.split(" ")[0] || "Developer"}</span> 👋
          </motion.h1>
          <p className="text-content-muted text-sm mt-1">
            Your AI-powered command center. Zero testers required.
          </p>
        </div>

        <Link href="/projects/new">
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            className="btn-primary flex items-center gap-2"
          >
            <Play className="w-4 h-4" />
            Run Tests
          </motion.button>
        </Link>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.07 }}
          >
            <StatCard {...s} loading={statsLoading} />
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* AI Recommendations */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="lg:col-span-2 glass-card p-5"
        >
          <div className="flex items-center gap-2 mb-4">
            <Zap className="w-5 h-5 text-brand-accent" />
            <h2 className="font-semibold text-content-primary">Jarviis Recommends</h2>
            <span className="badge badge-purple ml-auto">AI</span>
          </div>
          <div className="space-y-2">
            {aiRecommendations.map((r, i) => (
              <AIRecommendation key={i} {...r} />
            ))}
          </div>
        </motion.div>

        {/* Stats summary */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
          className="glass-card p-5"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-content-primary flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-brand-teal" />
              Quick Links
            </h2>
          </div>
          <div className="space-y-2">
            {[
              { label: "Launch Control", href: "/dashboard/deploy", icon: Rocket },
              { label: "Security Scanner", href: "/dashboard/security", icon: Shield },
              { label: "API Testing", href: "/dashboard/api-testing", icon: GitBranch },
              { label: "Ask Jarviis AI", href: "/dashboard/jarviis", icon: Zap },
            ].map(({ label, href, icon: Icon }) => (
              <Link key={href} href={href}>
                <div className="flex items-center gap-2 p-2.5 rounded-lg hover:bg-surface-overlay transition-colors cursor-pointer group">
                  <Icon className="w-4 h-4 text-content-muted group-hover:text-brand-accent transition-colors" />
                  <span className="text-sm text-content-secondary group-hover:text-content-primary transition-colors">{label}</span>
                  <ArrowRight className="w-3 h-3 text-content-muted ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
              </Link>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Empty state for first-time users */}
      {!hasProjects && !statsLoading && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="glass-card p-8 text-center border-dashed border-surface-muted"
        >
          <div className="flex justify-center gap-4 mb-5">
            {[Play, Rocket, Shield, Activity].map((Icon, i) => (
              <motion.div
                key={i}
                animate={{ y: [0, -8, 0] }}
                transition={{ duration: 2, repeat: Infinity, delay: i * 0.3 }}
                className="w-12 h-12 rounded-xl bg-surface-overlay border border-surface-border flex items-center justify-center"
              >
                <Icon className="w-6 h-6 text-brand-accent/60" />
              </motion.div>
            ))}
          </div>
          <h3 className="text-lg font-bold text-content-primary mb-2">
            Your Command Center is ready
          </h3>
          <p className="text-content-muted text-sm max-w-md mx-auto mb-5">
            Connect a project and JarviisAI will start autonomously testing, deploying, and healing your software — with zero manual intervention.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Link href="/projects/new">
              <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} className="btn-primary">
                Create First Project
              </motion.button>
            </Link>
            <Link href="/settings/integrations">
              <button className="btn-secondary">Connect GitHub</button>
            </Link>
          </div>
        </motion.div>
      )}
    </div>
  );
}


// ── Stat card ──────────────────────────────────────────────────
function StatCard({
  label, value, delta, icon: Icon, color, href
}: {
  label: string; value: string | number; delta?: string;
  icon: any; color: string; href?: string;
}) {
  const content = (
    <motion.div
      whileHover={{ y: -2, scale: 1.01 }}
      className="glass-card p-5 cursor-pointer glow-border group"
    >
      <div className="flex items-start justify-between mb-3">
        <div className={cn("p-2 rounded-lg", `bg-${color}/10 border border-${color}/20`)}>
          <Icon className={cn("w-5 h-5", `text-${color}`)} />
        </div>
        {delta && (
          <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full",
            delta.startsWith("+") ? "text-brand-teal bg-brand-teal/10" : "text-brand-crimson bg-brand-crimson/10"
          )}>
            {delta}
          </span>
        )}
      </div>
      <div className="text-2xl font-black text-content-primary mb-0.5">{value}</div>
      <div className="text-sm text-content-muted">{label}</div>
    </motion.div>
  );
  return href ? <Link href={href}>{content}</Link> : content;
}

// ── Activity item ──────────────────────────────────────────────
function ActivityItem({ type, title, time, status }: {
  type: "test" | "deploy" | "heal"; title: string; time: string; status: "pass" | "fail" | "running";
}) {
  const icons = { test: Play, deploy: Rocket, heal: Activity };
  const Icon = icons[type];
  const statusColors = {
    pass: "text-brand-teal", fail: "text-brand-crimson", running: "text-brand-accent"
  };
  const statusIcons = {
    pass: CheckCircle2, fail: XCircle, running: Clock
  };
  const StatusIcon = statusIcons[status];

  return (
    <div className="flex items-center gap-3 py-3 border-b border-surface-border last:border-0">
      <div className="w-8 h-8 rounded-lg bg-surface-overlay border border-surface-border flex items-center justify-center flex-shrink-0">
        <Icon className="w-4 h-4 text-content-muted" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-content-primary truncate">{title}</p>
        <p className="text-xs text-content-muted">{time}</p>
      </div>
      <StatusIcon className={cn("w-4 h-4 flex-shrink-0", statusColors[status])} />
    </div>
  );
}

// ── AI recommendation ──────────────────────────────────────────
function AIRecommendation({ text, action, href }: { text: string; action: string; href: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-start gap-3 p-3 bg-brand-accent/5 border border-brand-accent/20 rounded-lg"
    >
      <Zap className="w-4 h-4 text-brand-accent mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-content-primary">{text}</p>
      </div>
      <Link href={href}>
        <button className="text-xs text-brand-accent hover:text-brand-cyan font-medium whitespace-nowrap flex items-center gap-1 transition-colors">
          {action} <ArrowRight className="w-3 h-3" />
        </button>
      </Link>
    </motion.div>
  );
}

// ── Main dashboard ─────────────────────────────────────────────
export default function DashboardPage() {
  const { user } = useAuthStore();
  const greeting = new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening";

  // Placeholder data — will be replaced by React Query fetches in Phase 1
  const stats = [
    { label: "Tests Run Today", value: 0, icon: Play, color: "brand-accent", href: "/dashboard/test-runs" },
    { label: "Tests Passing", value: "—", icon: CheckCircle2, color: "brand-teal", href: "/dashboard/test-runs" },
    { label: "Deployments", value: 0, icon: Rocket, color: "brand-gold", href: "/dashboard/deployments" },
    { label: "Security Score", value: "—", icon: Shield, color: "brand-cyan", href: "/dashboard/security" },
  ];

  const recentActivity: any[] = [];

  const aiRecommendations = [
    {
      text: "Create your first project to start autonomous testing",
      action: "Create Project",
      href: "/projects/new",
    },
    {
      text: "Connect your GitHub repository to enable CI/CD triggers",
      action: "Connect GitHub",
      href: "/settings/integrations",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Welcome header */}
      <div className="flex items-start justify-between">
        <div>
          <motion.h1
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-2xl font-black text-content-primary"
          >
            {greeting},{" "}
            <span className="text-gradient">{user?.full_name?.split(" ")[0] || "Developer"}</span> 👋
          </motion.h1>
          <p className="text-content-muted text-sm mt-1">
            Your AI-powered command center. Zero testers required.
          </p>
        </div>

        <Link href="/projects/new">
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            className="btn-primary flex items-center gap-2"
          >
            <Play className="w-4 h-4" />
            Run Tests
          </motion.button>
        </Link>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.07 }}
          >
            <StatCard {...s} />
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* AI Recommendations */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="lg:col-span-2 glass-card p-5"
        >
          <div className="flex items-center gap-2 mb-4">
            <Zap className="w-5 h-5 text-brand-accent" />
            <h2 className="font-semibold text-content-primary">Jarviis Recommends</h2>
            <span className="badge badge-purple ml-auto">AI</span>
          </div>
          <div className="space-y-2">
            {aiRecommendations.map((r, i) => (
              <AIRecommendation key={i} {...r} />
            ))}
          </div>
        </motion.div>

        {/* Recent activity */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
          className="glass-card p-5"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-content-primary flex items-center gap-2">
              <Activity className="w-4 h-4 text-brand-teal" />
              Recent Activity
            </h2>
            <Link href="/dashboard/test-runs" className="text-xs text-brand-accent hover:text-brand-cyan transition-colors">
              View all →
            </Link>
          </div>
          {recentActivity.length === 0 ? (
            <div className="text-center py-8">
              <Play className="w-8 h-8 text-surface-border mx-auto mb-2" />
              <p className="text-sm text-content-muted">No test runs yet</p>
              <p className="text-xs text-content-muted mt-1">Create a project to get started</p>
            </div>
          ) : (
            recentActivity.map((a, i) => <ActivityItem key={i} {...a} />)
          )}
        </motion.div>
      </div>

      {/* Empty state for first-time users */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="glass-card p-8 text-center border-dashed border-surface-muted"
      >
        <div className="flex justify-center gap-4 mb-5">
          {[Play, Rocket, Shield, Activity].map((Icon, i) => (
            <motion.div
              key={i}
              animate={{ y: [0, -8, 0] }}
              transition={{ duration: 2, repeat: Infinity, delay: i * 0.3 }}
              className="w-12 h-12 rounded-xl bg-surface-overlay border border-surface-border flex items-center justify-center"
            >
              <Icon className="w-6 h-6 text-brand-accent/60" />
            </motion.div>
          ))}
        </div>
        <h3 className="text-lg font-bold text-content-primary mb-2">
          Your Command Center is ready
        </h3>
        <p className="text-content-muted text-sm max-w-md mx-auto mb-5">
          Connect a project and JarviisAI will start autonomously testing, deploying, and healing your software — with zero manual intervention.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Link href="/projects/new">
            <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} className="btn-primary">
              Create First Project
            </motion.button>
          </Link>
          <Link href="/settings/integrations">
            <button className="btn-secondary">Connect GitHub</button>
          </Link>
        </div>
      </motion.div>
    </div>
  );
}
