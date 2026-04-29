"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Play, Settings, GitBranch, Globe, Clock,
  CheckCircle2, XCircle, AlertCircle, Zap, BarChart3,
  RefreshCw, TrendingUp, Activity, Shield, Plus
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId, useOrgSlug } from "@/store/auth";
import { cn, formatRelativeTime, formatDate } from "@/lib/utils";
import { toast } from "sonner";

const STATUS_BADGE: Record<string, { label: string; classes: string }> = {
  passed:    { label: "Passed",    classes: "text-brand-teal bg-brand-teal/10 border-brand-teal/30" },
  failed:    { label: "Failed",    classes: "text-brand-crimson bg-brand-crimson/10 border-brand-crimson/30" },
  running:   { label: "Running",   classes: "text-brand-accent bg-brand-accent/10 border-brand-accent/30" },
  crawling:  { label: "Crawling",  classes: "text-brand-cyan bg-brand-cyan/10 border-brand-cyan/30" },
  generating:{ label: "AI",        classes: "text-brand-accent bg-brand-accent/10 border-brand-accent/30" },
  pending:   { label: "Pending",   classes: "text-content-muted bg-surface-border border-surface-border" },
  queued:    { label: "Queued",    classes: "text-content-muted bg-surface-border border-surface-border" },
  error:     { label: "Error",     classes: "text-brand-crimson bg-brand-crimson/10 border-brand-crimson/30" },
  cancelled: { label: "Cancelled", classes: "text-content-muted bg-surface-border border-surface-border" },
};

function RunRow({ run, orgId }: { run: any; orgId: string }) {
  const badge = STATUS_BADGE[run.status] || STATUS_BADGE.pending;
  const isActive = ["running","crawling","generating","queued"].includes(run.status);

  return (
    <Link href={`/projects/${run.project_id}/runs/${run.id}`}>
      <motion.div
        whileHover={{ x: 4 }}
        className="flex items-center gap-4 px-5 py-4 border-b border-surface-border last:border-0 hover:bg-surface-overlay transition-colors cursor-pointer group"
      >
        {/* Status */}
        <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full border min-w-[72px] text-center", badge.classes)}>
          {badge.label}
          {isActive && <span className="ml-1 animate-pulse">•</span>}
        </span>

        {/* Git context */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {run.git_branch && (
              <span className="flex items-center gap-1 text-xs text-content-muted font-mono">
                <GitBranch className="w-3 h-3" />
                {run.git_branch}
              </span>
            )}
            {run.git_commit_sha && (
              <span className="text-xs text-content-muted font-mono">
                {run.git_commit_sha.slice(0, 7)}
              </span>
            )}
            {!run.git_branch && (
              <span className="text-xs text-content-secondary">Manual run</span>
            )}
          </div>
          {run.git_commit_message && (
            <p className="text-xs text-content-muted truncate mt-0.5">{run.git_commit_message}</p>
          )}
        </div>

        {/* Results */}
        <div className="flex items-center gap-3 text-xs">
          {run.total_tests > 0 && (
            <>
              <span className="flex items-center gap-1 text-brand-teal">
                <CheckCircle2 className="w-3 h-3" />{run.passed_tests}
              </span>
              <span className="flex items-center gap-1 text-brand-crimson">
                <XCircle className="w-3 h-3" />{run.failed_tests}
              </span>
              <span className={cn("font-medium", run.pass_rate >= 80 ? "text-brand-teal" : run.pass_rate >= 50 ? "text-yellow-400" : "text-brand-crimson")}>
                {run.pass_rate}%
              </span>
            </>
          )}
        </div>

        {/* Duration */}
        <div className="text-xs text-content-muted flex items-center gap-1 w-16 justify-end">
          <Clock className="w-3 h-3" />
          {run.duration_display || "—"}
        </div>

        {/* Time */}
        <div className="text-xs text-content-muted w-20 text-right">
          {formatRelativeTime(run.created_at)}
        </div>
      </motion.div>
    </Link>
  );
}

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const qc = useQueryClient();
  const [tab, setTab] = useState<"runs" | "visual" | "settings">("runs");

  const { data: project, isLoading } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => apiClient.get(`/orgs/${orgId}/projects/${projectId}`).then(r => r.data),
    enabled: !!orgId && !!projectId,
  });

  const { data: runsData } = useQuery({
    queryKey: ["runs", projectId],
    queryFn: () => apiClient.get(`/orgs/${orgId}/projects/${projectId}/runs`).then(r => r.data),
    enabled: !!orgId && !!projectId,
    refetchInterval: 5000, // Poll every 5s for active runs
  });

  const triggerRun = useMutation({
    mutationFn: () => apiClient.post(`/orgs/${orgId}/projects/${projectId}/runs`, {}),
    onSuccess: (res) => {
      toast.success("Test run started!");
      qc.invalidateQueries({ queryKey: ["runs", projectId] });
      router.push(`/projects/${projectId}/runs/${res.data.id}`);
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || "Failed to start run");
    },
  });

  if (isLoading || !project) {
    return (
      <div className="flex items-center justify-center h-64">
        <Zap className="w-8 h-8 text-brand-accent animate-pulse" />
      </div>
    );
  }

  const runs = runsData?.runs || [];
  const hasActiveRun = runs.some((r: any) => ["running","crawling","generating","queued"].includes(r.status));

  const TABS = [
    { id: "runs", label: "Test Runs", icon: Play, count: runsData?.total },
    { id: "visual", label: "Visual Regression", icon: BarChart3 },
    { id: "settings", label: "Settings", icon: Settings },
  ];

  return (
    <div className="space-y-5">
      {/* Back */}
      <button onClick={() => router.push("/projects")} className="flex items-center gap-2 text-content-muted hover:text-content-primary transition-colors text-sm">
        <ArrowLeft className="w-4 h-4" /> All Projects
      </button>

      {/* Project header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-brand-accent/10 border border-brand-accent/30 flex items-center justify-center">
              <Globe className="w-6 h-6 text-brand-accent" />
            </div>
            <div>
              <h1 className="text-xl font-black text-content-primary">{project.name}</h1>
              <div className="flex items-center gap-3 mt-1">
                {project.project_url && (
                  <a href={project.project_url} target="_blank" rel="noopener noreferrer"
                     className="text-xs text-brand-accent hover:underline font-mono truncate max-w-xs">
                    {project.project_url}
                  </a>
                )}
                <span className="badge badge-purple text-xs capitalize">{project.project_type}</span>
              </div>
            </div>
          </div>

          <motion.button
            whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
            onClick={() => triggerRun.mutate()}
            disabled={triggerRun.isPending || hasActiveRun}
            className={cn(
              "btn-primary flex items-center gap-2",
              (triggerRun.isPending || hasActiveRun) && "opacity-60 cursor-not-allowed"
            )}
          >
            {triggerRun.isPending || hasActiveRun ? (
              <><RefreshCw className="w-4 h-4 animate-spin" /> Running...</>
            ) : (
              <><Play className="w-4 h-4" /> Run Tests</>
            )}
          </motion.button>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-4 gap-4 mt-5 pt-5 border-t border-surface-border">
          {[
            { label: "Total Runs", value: project.total_runs, icon: Activity },
            { label: "Pass Rate (30d)", value: project.pass_rate !== null ? `${project.pass_rate}%` : "—", icon: TrendingUp, highlight: project.pass_rate >= 80 ? "text-brand-teal" : project.pass_rate >= 50 ? "text-yellow-400" : null },
            { label: "Last Run", value: project.last_run_at ? formatRelativeTime(project.last_run_at) : "Never", icon: Clock },
            { label: "Status", value: project.last_run_status ? (STATUS_BADGE[project.last_run_status]?.label || "—") : "—", icon: Shield },
          ].map(({ label, value, icon: Icon, highlight }) => (
            <div key={label} className="text-center">
              <Icon className="w-4 h-4 text-content-muted mx-auto mb-1" />
              <div className={cn("font-bold text-lg", highlight || "text-content-primary")}>{value}</div>
              <div className="text-xs text-content-muted">{label}</div>
            </div>
          ))}
        </div>
      </motion.div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-surface-overlay border border-surface-border rounded-lg w-fit">
        {TABS.map(({ id, label, icon: Icon, count }) => (
          <button
            key={id}
            onClick={() => setTab(id as any)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all",
              tab === id
                ? "bg-brand-accent/15 text-brand-accent border border-brand-accent/25"
                : "text-content-muted hover:text-content-secondary"
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
            {count != null && (
              <span className="text-xs px-1.5 py-0.5 rounded-full bg-surface-border text-content-muted">{count}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <AnimatePresence mode="wait">
        {tab === "runs" && (
          <motion.div key="runs" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="glass-card overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3 border-b border-surface-border">
                <h2 className="font-semibold text-content-primary">Test Runs</h2>
                <button
                  onClick={() => qc.invalidateQueries({ queryKey: ["runs", projectId] })}
                  className="text-xs text-content-muted hover:text-brand-accent transition-colors flex items-center gap-1"
                >
                  <RefreshCw className="w-3 h-3" /> Refresh
                </button>
              </div>
              {runs.length === 0 ? (
                <div className="py-16 text-center">
                  <Play className="w-8 h-8 text-surface-border mx-auto mb-3" />
                  <p className="text-content-muted text-sm">No test runs yet</p>
                  <p className="text-content-muted text-xs mt-1">Click "Run Tests" to start your first autonomous test run</p>
                </div>
              ) : (
                runs.map((run: any) => <RunRow key={run.id} run={run} orgId={orgId} />)
              )}
            </div>
          </motion.div>
        )}

        {tab === "visual" && (
          <motion.div key="visual" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="glass-card p-8 text-center">
              <BarChart3 className="w-10 h-10 text-brand-accent mx-auto mb-3" />
              <h3 className="font-semibold text-content-primary mb-2">Visual Regression</h3>
              <p className="text-content-muted text-sm max-w-md mx-auto">
                Run a test first — JarviisAI will capture baseline screenshots and detect
                visual regressions on every subsequent run.
              </p>
            </div>
          </motion.div>
        )}

        {tab === "settings" && (
          <motion.div key="settings" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <Link href={`/projects/${projectId}/settings`}>
              <div className="glass-card p-8 text-center cursor-pointer hover:border-brand-accent/40 transition-colors">
                <Settings className="w-10 h-10 text-brand-accent mx-auto mb-3" />
                <h3 className="font-semibold text-content-primary mb-2">Project Settings</h3>
                <p className="text-content-muted text-sm">Configure GitHub integration, browsers, auth, and more</p>
              </div>
            </Link>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
