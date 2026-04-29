"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Play, CheckCircle2, XCircle, Clock, RefreshCw,
  ChevronRight, GitBranch, Calendar, Filter
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId } from "@/store/auth";
import { cn, formatRelativeTime } from "@/lib/utils";
import Link from "next/link";
import { FilterBar, FilterState } from "@/components/filters/FilterBar";

const STATUS_CONFIG: Record<string, { icon: any; color: string; bg: string; label: string }> = {
  passed:    { icon: CheckCircle2, color: "text-brand-teal",    bg: "bg-brand-teal/10",    label: "Passed"   },
  failed:    { icon: XCircle,      color: "text-brand-crimson", bg: "bg-brand-crimson/10", label: "Failed"   },
  running:   { icon: RefreshCw,    color: "text-brand-accent",  bg: "bg-brand-accent/10",  label: "Running"  },
  pending:   { icon: Clock,        color: "text-content-muted", bg: "bg-surface-border",   label: "Pending"  },
  cancelled: { icon: XCircle,      color: "text-content-muted", bg: "bg-surface-border",   label: "Cancelled"},
  error:     { icon: XCircle,      color: "text-brand-gold",    bg: "bg-brand-gold/10",    label: "Error"    },
};

export default function TestRunsPage() {
  const orgId = useOrgId();
  const [filters, setFilters] = useState<FilterState>({});
  const [page, setPage] = useState(1);

  // First fetch all projects to get runs across them
  const { data: projectsData } = useQuery({
    queryKey: ["projects-for-runs", orgId],
    queryFn: () => apiClient.get(`/orgs/${orgId}/projects?page_size=20`).then(r => r.data),
    enabled: !!orgId,
  });

  const projects = projectsData?.projects || [];

  // Fetch recent runs for each project (limit to first 5 projects for perf)
  const { data: runsData, isLoading, refetch } = useQuery({
    queryKey: ["all-test-runs", orgId, filters.status, filters.dateFrom, page],
    queryFn: async () => {
      const allRuns: any[] = [];
      const slice = projects.slice(0, 5);
      await Promise.all(slice.map(async (proj: any) => {
        try {
          const params: Record<string, any> = { page_size: 20, page };
          if (filters.status) params.status_filter = filters.status;
          const r = await apiClient.get(
            `/orgs/${orgId}/projects/${proj.id}/runs`, { params }
          );
          const runs = r.data.runs || [];
          runs.forEach((run: any) => {
            allRuns.push({ ...run, project_name: proj.name, project_id: proj.id });
          });
        } catch {
          // Skip failed project
        }
      }));
      // Sort most recent first
      allRuns.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      return allRuns;
    },
    enabled: !!orgId && projects.length > 0,
    refetchInterval: 15_000,
  });

  const runs = runsData || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
            <Play className="w-7 h-7 text-brand-accent" /> Test Runs
          </h1>
          <p className="text-content-muted text-sm mt-1">All test runs across your projects</p>
        </div>
        <div className="flex items-center gap-3">
          <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
            onClick={() => refetch()}
            className="p-2 border border-surface-border rounded-lg hover:border-brand-accent/40 text-content-muted hover:text-brand-accent transition-all">
            <RefreshCw className="w-4 h-4" />
          </motion.button>
          <Link href="/projects/new">
            <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
              className="btn-primary flex items-center gap-2">
              <Play className="w-4 h-4" /> New Run
            </motion.button>
          </Link>
        </div>
      </div>

      {/* Filters */}
      <FilterBar
        filters={filters}
        onChange={setFilters}
        availableFilters={["status", "date", "project"]}
        projects={projects.map((p: any) => ({ id: p.id, name: p.name }))}
      />

      {/* Runs table */}
      <div className="glass-card overflow-hidden">
        <div className="grid grid-cols-12 gap-3 px-5 py-3 border-b border-surface-border text-xs font-semibold text-content-muted uppercase tracking-wider">
          <div className="col-span-2">Status</div>
          <div className="col-span-3">Project</div>
          <div className="col-span-2">Branch</div>
          <div className="col-span-2">Tests</div>
          <div className="col-span-2">Started</div>
          <div className="col-span-1"></div>
        </div>

        {isLoading ? (
          <div className="p-6 space-y-3">
            {[1,2,3,4,5].map(i => (
              <div key={i} className="grid grid-cols-12 gap-3 animate-pulse">
                {[2,3,2,2,2,1].map((span, j) => (
                  <div key={j} className={`col-span-${span} h-10 bg-surface-border rounded`} />
                ))}
              </div>
            ))}
          </div>
        ) : runs.length === 0 ? (
          <div className="py-16 text-center">
            <Play className="w-12 h-12 text-surface-muted mx-auto mb-4" />
            <p className="text-content-primary font-semibold mb-1">No test runs yet</p>
            <p className="text-content-muted text-sm mb-4">
              Create a project and run your first automated test suite
            </p>
            <Link href="/projects/new">
              <button className="btn-primary">Create First Project</button>
            </Link>
          </div>
        ) : (
          runs.map((run: any) => {
            const cfg = STATUS_CONFIG[run.status] || STATUS_CONFIG.pending;
            const Icon = cfg.icon;
            const passRate = run.total_tests > 0
              ? Math.round(run.passed_tests / run.total_tests * 100)
              : null;

            return (
              <Link key={run.id} href={`/projects/${run.project_id}/runs/${run.id}`}>
                <motion.div whileHover={{ x: 2 }}
                  className="grid grid-cols-12 gap-3 items-center px-5 py-3.5 border-b border-surface-border last:border-0 hover:bg-surface-overlay transition-all cursor-pointer">

                  {/* Status */}
                  <div className="col-span-2 flex items-center gap-2">
                    <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0", cfg.bg)}>
                      <Icon className={cn("w-3.5 h-3.5", cfg.color,
                        run.status === "running" && "animate-spin")} />
                    </div>
                    <span className={cn("text-xs font-medium", cfg.color)}>{cfg.label}</span>
                  </div>

                  {/* Project */}
                  <div className="col-span-3 min-w-0">
                    <p className="text-sm font-medium text-content-primary truncate">{run.project_name}</p>
                    <p className="text-xs text-content-muted font-mono truncate">{run.id?.slice(0, 8)}…</p>
                  </div>

                  {/* Branch */}
                  <div className="col-span-2 flex items-center gap-1.5 min-w-0">
                    <GitBranch className="w-3 h-3 text-content-muted flex-shrink-0" />
                    <span className="text-xs text-content-secondary font-mono truncate">
                      {run.git_branch || "manual"}
                    </span>
                  </div>

                  {/* Tests */}
                  <div className="col-span-2">
                    {run.total_tests > 0 ? (
                      <div>
                        <span className="text-sm font-mono text-content-primary">
                          {run.passed_tests}/{run.total_tests}
                        </span>
                        {passRate !== null && (
                          <span className={cn("text-xs ml-1.5", passRate >= 80 ? "text-brand-teal" : "text-brand-crimson")}>
                            {passRate}%
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-content-muted">—</span>
                    )}
                  </div>

                  {/* Time */}
                  <div className="col-span-2 flex items-center gap-1.5">
                    <Calendar className="w-3 h-3 text-content-muted flex-shrink-0" />
                    <span className="text-xs text-content-muted">
                      {run.created_at ? formatRelativeTime(run.created_at) : "—"}
                    </span>
                  </div>

                  {/* Arrow */}
                  <div className="col-span-1 flex justify-end">
                    <ChevronRight className="w-4 h-4 text-content-muted" />
                  </div>
                </motion.div>
              </Link>
            );
          })
        )}
      </div>
    </div>
  );
}
