"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft, CheckCircle2, XCircle, Clock, Zap, GitBranch,
  Terminal, Play, AlertCircle, Activity, RefreshCw,
  ChevronDown, ChevronRight, Eye, BarChart3, Heart
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId, useOrgSlug } from "@/store/auth";
import { cn, formatRelativeTime } from "@/lib/utils";
import TestRunMonitor from "@/components/dashboard/TestRunMonitor";

const ACTIVE_STATUSES = new Set(["pending","queued","crawling","generating","running"]);
const STAGE_LABELS: Record<string, string> = {
  crawling:   "🕷️  Crawling your app...",
  generating: "🤖 Claude is writing tests...",
  running:    "⚡ Executing tests...",
  healing:    "🔧 Auto-healing failures...",
};

function TestCaseRow({ tc }: { tc: any }) {
  const [open, setOpen] = useState(false);
  const isPassed = tc.status === "passed";
  const isFailed = tc.status === "failed";

  return (
    <div className="border-b border-surface-border last:border-0">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-3 w-full px-5 py-3 hover:bg-surface-overlay transition-colors text-left"
      >
        {isPassed && <CheckCircle2 className="w-4 h-4 text-brand-teal flex-shrink-0" />}
        {isFailed && <XCircle className="w-4 h-4 text-brand-crimson flex-shrink-0" />}
        {!isPassed && !isFailed && <Clock className="w-4 h-4 text-content-muted flex-shrink-0" />}

        <span className={cn("text-sm flex-1 truncate", isFailed ? "text-brand-crimson" : "text-content-primary")}>
          {tc.name}
        </span>

        {tc.self_healed && (
          <span className="flex items-center gap-1 text-xs text-brand-teal bg-brand-teal/10 border border-brand-teal/20 px-2 py-0.5 rounded-full">
            <Heart className="w-3 h-3" /> Auto-healed
          </span>
        )}

        {tc.duration_ms && (
          <span className="text-xs text-content-muted">{tc.duration_ms}ms</span>
        )}

        {tc.retry_count > 0 && (
          <span className="text-xs text-content-muted">{tc.retry_count} retries</span>
        )}

        {isFailed && (open ? <ChevronDown className="w-4 h-4 text-content-muted" /> : <ChevronRight className="w-4 h-4 text-content-muted" />)}
      </button>

      {open && isFailed && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          className="px-5 pb-4 space-y-3"
        >
          {tc.error_message && (
            <div className="bg-brand-crimson/5 border border-brand-crimson/20 rounded-lg p-3">
              <p className="text-xs font-semibold text-brand-crimson mb-1">Error</p>
              <pre className="text-xs text-content-secondary whitespace-pre-wrap font-mono">{tc.error_message}</pre>
            </div>
          )}
          {tc.ai_failure_explanation && (
            <div className="bg-brand-accent/5 border border-brand-accent/20 rounded-lg p-3">
              <p className="text-xs font-semibold text-brand-accent mb-1 flex items-center gap-1">
                <Zap className="w-3 h-3" /> AI Analysis
              </p>
              <p className="text-xs text-content-secondary">{tc.ai_failure_explanation}</p>
            </div>
          )}
          {tc.ai_fix_suggestion && (
            <div className="bg-brand-teal/5 border border-brand-teal/20 rounded-lg p-3">
              <p className="text-xs font-semibold text-brand-teal mb-1">Suggested Fix</p>
              <p className="text-xs text-content-secondary">{tc.ai_fix_suggestion}</p>
            </div>
          )}
          {tc.screenshot_url && (
            <div>
              <p className="text-xs font-semibold text-content-muted mb-1 flex items-center gap-1">
                <Eye className="w-3 h-3" /> Screenshot
              </p>
              <img src={tc.screenshot_url} alt="Failure screenshot" className="rounded-lg border border-surface-border max-h-48 object-cover" />
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}

export default function RunDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;
  const runId = params.runId as string;
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const [activeTab, setActiveTab] = useState<"monitor"|"cases"|"ai">("monitor");

  const { data: run, isLoading, refetch } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => apiClient.get(`/orgs/${orgId}/runs/${runId}`).then(r => r.data),
    enabled: !!orgId && !!runId,
    refetchInterval: (data) => ACTIVE_STATUSES.has(data?.status) ? 3000 : false,
  });

  const { data: casesData } = useQuery({
    queryKey: ["run-cases", runId],
    queryFn: () => apiClient.get(`/orgs/${orgId}/runs/${runId}/cases`).then(r => r.data),
    enabled: !!orgId && !!runId && !ACTIVE_STATUSES.has(run?.status),
  });

  if (isLoading || !run) {
    return (
      <div className="flex items-center justify-center h-64">
        <Zap className="w-8 h-8 text-brand-accent animate-pulse" />
      </div>
    );
  }

  const isActive = ACTIVE_STATUSES.has(run.status);
  const cases = casesData?.cases || [];
  const failedCases = cases.filter((c: any) => c.status === "failed");
  const healedCases = cases.filter((c: any) => c.self_healed);

  const TABS = [
    { id: "monitor", label: isActive ? "Live Monitor" : "Summary", icon: Activity },
    { id: "cases", label: `Test Cases (${cases.length})`, icon: CheckCircle2 },
    { id: "ai", label: "AI Analysis", icon: Zap },
  ];

  return (
    <div className="space-y-5">
      {/* Back */}
      <button onClick={() => router.push(`/projects/${projectId}`)} className="flex items-center gap-2 text-content-muted hover:text-content-primary transition-colors text-sm">
        <ArrowLeft className="w-4 h-4" /> Back to Project
      </button>

      {/* Run header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="text-xs font-mono text-content-muted">Run #{runId.slice(0, 8)}</span>
              {run.git_branch && (
                <span className="flex items-center gap-1 text-xs font-mono text-brand-cyan bg-brand-cyan/10 border border-brand-cyan/20 px-2 py-0.5 rounded-full">
                  <GitBranch className="w-3 h-3" />
                  {run.git_branch}
                </span>
              )}
              {run.git_commit_sha && (
                <span className="text-xs font-mono text-content-muted">{run.git_commit_sha.slice(0, 7)}</span>
              )}
            </div>
            {run.git_commit_message && (
              <p className="text-sm text-content-secondary">{run.git_commit_message}</p>
            )}
            <p className="text-xs text-content-muted mt-1">{formatRelativeTime(run.created_at)}</p>
          </div>

          <button onClick={() => refetch()} className="text-content-muted hover:text-brand-accent transition-colors">
            <RefreshCw className={cn("w-4 h-4", isActive && "animate-spin")} />
          </button>
        </div>

        {/* Quick stats */}
        {!isActive && run.total_tests > 0 && (
          <div className="grid grid-cols-5 gap-3 mt-4 pt-4 border-t border-surface-border">
            {[
              { label: "Total", value: run.total_tests, color: "text-content-primary" },
              { label: "Passed", value: run.passed_tests, color: "text-brand-teal" },
              { label: "Failed", value: run.failed_tests, color: "text-brand-crimson" },
              { label: "Healed", value: healedCases.length, color: "text-brand-teal" },
              { label: "Pass Rate", value: `${run.pass_rate}%`, color: run.pass_rate >= 80 ? "text-brand-teal" : run.pass_rate >= 50 ? "text-yellow-400" : "text-brand-crimson" },
            ].map(({ label, value, color }) => (
              <div key={label} className="text-center p-2 bg-surface-overlay rounded-lg border border-surface-border">
                <div className={cn("text-lg font-black", color)}>{value}</div>
                <div className="text-xs text-content-muted">{label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Active stage indicator */}
        {isActive && STAGE_LABELS[run.status] && (
          <div className="mt-4 flex items-center gap-2 text-sm text-brand-accent">
            <Activity className="w-4 h-4 animate-pulse" />
            {STAGE_LABELS[run.status]}
          </div>
        )}
      </motion.div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-surface-overlay border border-surface-border rounded-lg w-fit">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id as any)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all",
              activeTab === id ? "bg-brand-accent/15 text-brand-accent border border-brand-accent/25" : "text-content-muted hover:text-content-secondary"
            )}
          >
            <Icon className="w-4 h-4" /> {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <AnimatePresence mode="wait">
        {activeTab === "monitor" && (
          <motion.div key="monitor" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            {isActive ? (
              <TestRunMonitor
                runId={runId}
                initialStatus={run.status}
                totalTests={run.ai_test_plan?.total_tests || 0}
                onComplete={() => refetch()}
              />
            ) : (
              <div className="glass-card p-8 text-center">
                {run.status === "passed" ? (
                  <CheckCircle2 className="w-12 h-12 text-brand-teal mx-auto mb-3" />
                ) : run.status === "failed" ? (
                  <XCircle className="w-12 h-12 text-brand-crimson mx-auto mb-3" />
                ) : (
                  <AlertCircle className="w-12 h-12 text-brand-crimson mx-auto mb-3" />
                )}
                <h3 className="font-bold text-content-primary text-lg mb-1 capitalize">{run.status}</h3>
                {run.duration_display && <p className="text-content-muted text-sm">Duration: {run.duration_display}</p>}
                {run.error_message && (
                  <div className="mt-4 bg-brand-crimson/5 border border-brand-crimson/20 rounded-lg p-3 text-left">
                    <p className="text-xs font-semibold text-brand-crimson mb-1">Error</p>
                    <pre className="text-xs text-content-secondary">{run.error_message}</pre>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        )}

        {activeTab === "cases" && (
          <motion.div key="cases" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="glass-card overflow-hidden">
              <div className="px-5 py-3 border-b border-surface-border flex items-center justify-between">
                <h2 className="font-semibold text-content-primary">Test Cases</h2>
                <div className="flex items-center gap-3 text-xs text-content-muted">
                  <span className="text-brand-teal">{run.passed_tests} passed</span>
                  <span className="text-brand-crimson">{run.failed_tests} failed</span>
                </div>
              </div>
              {cases.length === 0 ? (
                <div className="py-10 text-center text-content-muted text-sm">
                  {isActive ? "Tests running..." : "No test results yet"}
                </div>
              ) : (
                cases.map((tc: any) => <TestCaseRow key={tc.id} tc={tc} />)
              )}
            </div>
          </motion.div>
        )}

        {activeTab === "ai" && (
          <motion.div key="ai" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="glass-card p-5 space-y-4">
              <h2 className="font-semibold text-content-primary flex items-center gap-2">
                <Zap className="w-4 h-4 text-brand-accent" /> AI Analysis
              </h2>

              {run.ai_summary && (
                <div className="bg-brand-accent/5 border border-brand-accent/20 rounded-lg p-4">
                  <p className="text-xs font-semibold text-brand-accent mb-2">Run Summary</p>
                  <p className="text-sm text-content-secondary">{run.ai_summary}</p>
                </div>
              )}

              {run.ai_test_plan && (
                <div className="bg-surface-overlay border border-surface-border rounded-lg p-4">
                  <p className="text-xs font-semibold text-content-secondary mb-2">Test Plan</p>
                  <p className="text-sm text-content-secondary">{run.ai_test_plan.summary}</p>
                  {run.ai_test_plan.coverage_areas?.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {run.ai_test_plan.coverage_areas.map((area: string) => (
                        <span key={area} className="text-xs px-2 py-0.5 bg-surface-border rounded-full text-content-muted capitalize">{area}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {healedCases.length > 0 && (
                <div className="bg-brand-teal/5 border border-brand-teal/20 rounded-lg p-4">
                  <p className="text-xs font-semibold text-brand-teal mb-2 flex items-center gap-1">
                    <Heart className="w-3 h-3" /> Auto-Healing Applied
                  </p>
                  <p className="text-sm text-content-secondary">
                    {healedCases.length} test{healedCases.length !== 1 ? "s" : ""} were automatically healed by JarviisAI.
                  </p>
                </div>
              )}

              {!run.ai_summary && !run.ai_test_plan && (
                <div className="py-8 text-center text-content-muted text-sm">
                  <Zap className="w-8 h-8 mx-auto mb-2 text-surface-border" />
                  AI analysis will appear here after the run completes.
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
