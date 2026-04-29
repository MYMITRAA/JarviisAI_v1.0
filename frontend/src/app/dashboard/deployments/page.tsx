"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Rocket, CheckCircle2, XCircle, Clock, RefreshCw,
  GitBranch, Shield, RotateCcw, AlertCircle, Filter,
  ChevronDown, Terminal
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId, useOrgSlug } from "@/store/auth";
import { cn, formatRelativeTime, formatDate } from "@/lib/utils";
import { toast } from "sonner";

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: any }> = {
  running:    { label: "Running",    color: "text-brand-teal",    bg: "bg-brand-teal/10",    icon: CheckCircle2 },
  deploying:  { label: "Deploying",  color: "text-brand-accent",  bg: "bg-brand-accent/10",  icon: Rocket },
  building:   { label: "Building",   color: "text-brand-cyan",    bg: "bg-brand-cyan/10",    icon: RefreshCw },
  pending:    { label: "Pending",    color: "text-content-muted", bg: "bg-surface-border",   icon: Clock },
  failed:     { label: "Failed",     color: "text-brand-crimson", bg: "bg-brand-crimson/10", icon: XCircle },
  rolled_back:{ label: "Rolled back",color: "text-content-muted", bg: "bg-surface-border",   icon: RotateCcw },
  cancelled:  { label: "Cancelled",  color: "text-content-muted", bg: "bg-surface-border",   icon: XCircle },
  degraded:   { label: "Degraded",   color: "text-brand-gold",    bg: "bg-brand-gold/10",    icon: AlertCircle },
};

function DeploymentCard({ dep, orgId }: { dep: any; orgId: string }) {
  const [expanded, setExpanded] = useState(false);
  const [rollbackConfirm, setRollbackConfirm] = useState(false);
  const qc = useQueryClient();
  const status = STATUS_CONFIG[dep.status] || STATUS_CONFIG.pending;
  const StatusIcon = status.icon;
  const isActive = ["deploying", "building", "pending"].includes(dep.status);
  const canRollback = dep.status === "running" && !dep.is_rollback;

  const rollback = useMutation({
    mutationFn: () => apiClient.post(`/deploy/orgs/${orgId}/deployments/${dep.id}/rollback`, {
      deployment_id: dep.id,
      reason: "Manual rollback from dashboard",
    }),
    onSuccess: () => {
      toast.success("Rollback initiated");
      setRollbackConfirm(false);
      qc.invalidateQueries({ queryKey: ["deployments"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Rollback failed"),
  });

  return (
    <motion.div
      layout
      className="glass-card overflow-hidden"
    >
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-4 px-5 py-4 hover:bg-surface-overlay transition-colors text-left"
      >
        {/* Status */}
        <div className={cn("flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium min-w-[100px]", status.bg, status.color)}>
          <StatusIcon className={cn("w-3 h-3", isActive && "animate-spin")} />
          {status.label}
        </div>

        {/* Git info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {dep.git_branch && (
              <span className="flex items-center gap-1 text-xs font-mono text-brand-cyan">
                <GitBranch className="w-3 h-3" />
                {dep.git_branch}
              </span>
            )}
            {dep.image_tag && (
              <span className="text-xs bg-surface-border px-1.5 py-0.5 rounded font-mono text-content-muted">
                :{dep.image_tag}
              </span>
            )}
            {dep.is_rollback && (
              <span className="text-xs bg-brand-gold/10 text-brand-gold border border-brand-gold/20 px-1.5 py-0.5 rounded">
                ↩ rollback
              </span>
            )}
          </div>
          {dep.git_commit_message && (
            <p className="text-xs text-content-muted truncate mt-0.5">{dep.git_commit_message}</p>
          )}
        </div>

        {/* Meta */}
        <div className="flex items-center gap-4 text-xs text-content-muted">
          {dep.health_check_passed !== null && dep.health_check_passed !== undefined && (
            <span className={cn("flex items-center gap-1", dep.health_check_passed ? "text-brand-teal" : "text-brand-crimson")}>
              <Shield className="w-3 h-3" />
              {dep.health_check_passed ? `${dep.health_check_response_ms}ms` : "Fail"}
            </span>
          )}
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {dep.duration_display || "—"}
          </span>
          <span>{formatRelativeTime(dep.created_at)}</span>
        </div>

        <ChevronDown className={cn("w-4 h-4 text-content-muted transition-transform", expanded && "rotate-180")} />
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-t border-surface-border overflow-hidden"
          >
            <div className="p-5 space-y-4">
              {/* Details grid */}
              <div className="grid grid-cols-3 gap-3 text-xs">
                {[
                  { label: "Environment", value: dep.environment_id?.slice(0, 8) + "..." },
                  { label: "Started", value: dep.started_at ? formatDate(dep.started_at) : "—" },
                  { label: "Completed", value: dep.completed_at ? formatDate(dep.completed_at) : "—" },
                  { label: "Strategy", value: dep.strategy || "rolling" },
                  { label: "Test Gate", value: dep.test_gate_passed === true ? "✅ Passed" : dep.test_gate_passed === false ? "❌ Failed" : "—" },
                  { label: "Rollback", value: dep.is_rollback ? "Yes" : "No" },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-surface-overlay rounded-lg p-2.5">
                    <p className="text-content-muted mb-0.5">{label}</p>
                    <p className="text-content-primary font-mono">{value}</p>
                  </div>
                ))}
              </div>

              {/* Error message */}
              {dep.error_message && (
                <div className="bg-brand-crimson/5 border border-brand-crimson/20 rounded-lg p-3">
                  <p className="text-xs font-semibold text-brand-crimson mb-1">
                    Error {dep.error_stage && `(${dep.error_stage})`}
                  </p>
                  <pre className="text-xs text-content-secondary whitespace-pre-wrap">{dep.error_message}</pre>
                </div>
              )}

              {/* Actions */}
              {canRollback && (
                <div className="flex gap-2 pt-1">
                  {!rollbackConfirm ? (
                    <button
                      onClick={() => setRollbackConfirm(true)}
                      className="flex items-center gap-1.5 px-3 py-1.5 border border-brand-gold/40 text-brand-gold text-xs rounded-lg hover:bg-brand-gold/10 transition-colors"
                    >
                      <RotateCcw className="w-3 h-3" /> Rollback
                    </button>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-content-muted">Confirm rollback?</span>
                      <button
                        onClick={() => rollback.mutate()}
                        disabled={rollback.isPending}
                        className="px-3 py-1.5 bg-brand-gold text-black text-xs rounded-lg font-medium hover:bg-brand-gold/80 transition-colors"
                      >
                        {rollback.isPending ? "Rolling back..." : "Yes, rollback"}
                      </button>
                      <button
                        onClick={() => setRollbackConfirm(false)}
                        className="px-3 py-1.5 border border-surface-border text-content-muted text-xs rounded-lg hover:border-surface-muted transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function DeploymentsPage() {
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const { data: projects } = useQuery({
    queryKey: ["projects", orgId],
    queryFn: () => apiClient.get(`/orgs/${orgId}/projects`).then(r => r.data),
    enabled: !!orgId,
  });

  const projectList = projects?.projects || [];

  const STATUS_FILTERS = ["all", "running", "deploying", "failed", "rolled_back"];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-black text-content-primary">Deployments</h1>
          <p className="text-content-muted text-sm mt-1">All deployment history across your environments</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        <Filter className="w-4 h-4 text-content-muted" />
        {STATUS_FILTERS.map(f => (
          <button
            key={f}
            onClick={() => setStatusFilter(f)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all",
              statusFilter === f
                ? "bg-brand-accent/15 text-brand-accent border border-brand-accent/30"
                : "border border-surface-border text-content-muted hover:border-surface-muted"
            )}
          >
            {f === "all" ? "All" : STATUS_CONFIG[f]?.label || f}
          </button>
        ))}
      </div>

      {/* Per-project deployment lists */}
      {projectList.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <Rocket className="w-10 h-10 text-surface-muted mx-auto mb-3" />
          <p className="text-content-muted">No projects found — create one to start deploying</p>
        </div>
      ) : (
        projectList.map((project: any) => (
          <ProjectDeployments
            key={project.id}
            project={project}
            orgId={orgId}
            statusFilter={statusFilter}
          />
        ))
      )}
    </div>
  );
}

function ProjectDeployments({ project, orgId, statusFilter }: { project: any; orgId: string; statusFilter: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["deployments", project.id, statusFilter],
    queryFn: () => apiClient.get(`/deploy/orgs/${orgId}/projects/${project.id}/deployments?page_size=5`).then(r => r.data),
    enabled: !!orgId,
    refetchInterval: 10000,
  });

  const deployments = (data?.deployments || []).filter((d: any) =>
    statusFilter === "all" || d.status === statusFilter
  );

  if (deployments.length === 0 && !isLoading) return null;

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <div className="w-6 h-6 rounded bg-brand-accent/10 border border-brand-accent/20 flex items-center justify-center text-xs font-bold text-brand-accent">
          {project.name[0]}
        </div>
        <h3 className="text-sm font-semibold text-content-primary">{project.name}</h3>
        <span className="text-xs text-content-muted">({data?.total || 0} total)</span>
      </div>
      <div className="space-y-2">
        {isLoading ? (
          <div className="glass-card p-4 animate-pulse">
            <div className="h-4 bg-surface-border rounded w-2/3" />
          </div>
        ) : (
          deployments.map((dep: any) => (
            <DeploymentCard key={dep.id} dep={dep} orgId={orgId} />
          ))
        )}
      </div>
    </div>
  );
}
