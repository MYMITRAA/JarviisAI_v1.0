"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import {
  Rocket, CheckCircle2, XCircle, Clock, RefreshCw,
  GitBranch, Server, ArrowRight, Zap, Play,
  ChevronDown, BarChart3, Shield, AlertCircle, Settings
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId, useOrgSlug } from "@/store/auth";
import { cn, formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: any }> = {
  running:    { label: "Running",     color: "text-brand-teal",    bg: "bg-brand-teal/10",    icon: CheckCircle2 },
  deploying:  { label: "Deploying",   color: "text-brand-accent",  bg: "bg-brand-accent/10",  icon: Rocket },
  building:   { label: "Building",    color: "text-brand-cyan",    bg: "bg-brand-cyan/10",    icon: RefreshCw },
  pending:    { label: "Pending",     color: "text-content-muted", bg: "bg-surface-border",   icon: Clock },
  failed:     { label: "Failed",      color: "text-brand-crimson", bg: "bg-brand-crimson/10", icon: XCircle },
  rolled_back:{ label: "Rolled back", color: "text-content-muted", bg: "bg-surface-border",   icon: RefreshCw },
  cancelled:  { label: "Cancelled",   color: "text-content-muted", bg: "bg-surface-border",   icon: XCircle },
};

const TIER_CONFIG: Record<string, { color: string; label: string; bg: string }> = {
  development: { color: "text-brand-cyan",    bg: "bg-brand-cyan/10",    label: "Dev" },
  staging:     { color: "text-brand-gold",    bg: "bg-brand-gold/10",    label: "Staging" },
  production:  { color: "text-brand-crimson", bg: "bg-brand-crimson/10", label: "Production" },
  custom:      { color: "text-content-muted", bg: "bg-surface-border",   label: "Custom" },
};

function DeploymentRow({ dep }: { dep: any }) {
  const status = STATUS_CONFIG[dep.status] || STATUS_CONFIG.pending;
  const StatusIcon = status.icon;
  const isActive = ["deploying", "building", "pending"].includes(dep.status);

  return (
    <motion.div
      whileHover={{ x: 3 }}
      className="flex items-center gap-4 px-5 py-3.5 border-b border-surface-border last:border-0 hover:bg-surface-overlay transition-colors"
    >
      <div className={cn("flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium min-w-[96px]", status.bg, status.color)}>
        <StatusIcon className={cn("w-3 h-3", isActive && "animate-spin")} />
        {status.label}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {dep.git_branch && (
            <span className="flex items-center gap-1 text-xs font-mono text-brand-cyan">
              <GitBranch className="w-3 h-3" />
              {dep.git_branch}
            </span>
          )}
          {dep.image_tag && (
            <span className="text-xs font-mono text-content-muted bg-surface-border px-1.5 py-0.5 rounded">
              :{dep.image_tag}
            </span>
          )}
          {dep.is_rollback && (
            <span className="text-xs text-brand-gold bg-brand-gold/10 border border-brand-gold/20 px-1.5 py-0.5 rounded">
              ↩ rollback
            </span>
          )}
        </div>
      </div>

      <div className="text-xs text-content-muted flex items-center gap-1">
        <Clock className="w-3 h-3" />
        {dep.duration_display || "—"}
      </div>

      {dep.health_check_passed !== null && dep.health_check_passed !== undefined && (
        <div className={cn("flex items-center gap-1 text-xs", dep.health_check_passed ? "text-brand-teal" : "text-brand-crimson")}>
          <Shield className="w-3 h-3" />
          {dep.health_check_passed ? "Healthy" : "Unhealthy"}
        </div>
      )}

      <div className="text-xs text-content-muted w-20 text-right">
        {formatRelativeTime(dep.created_at)}
      </div>
    </motion.div>
  );
}

function EnvironmentCard({ env, projectId, orgId }: { env: any; projectId: string; orgId: string }) {
  const [showDeploy, setShowDeploy] = useState(false);
  const [imageTag, setImageTag] = useState("latest");
  const qc = useQueryClient();
  const tierCfg = TIER_CONFIG[env.tier] || TIER_CONFIG.custom;

  const deploy = useMutation({
    mutationFn: () => apiClient.post(`/deploy/orgs/${orgId}/projects/${projectId}/deployments`, {
      environment_id: env.id,
      image_tag: imageTag,
    }),
    onSuccess: (res) => {
      toast.success(`Deployment to ${env.tier} started!`);
      setShowDeploy(false);
      qc.invalidateQueries({ queryKey: ["deployments", projectId] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Deployment failed to start"),
  });

  return (
    <motion.div whileHover={{ y: -2 }} className="glass-card p-5 glow-border">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className={cn("text-xs font-bold px-2 py-0.5 rounded-full", tierCfg.bg, tierCfg.color)}>
              {tierCfg.label}
            </span>
            <span className="text-sm font-semibold text-content-primary">{env.name}</span>
          </div>
          {env.current_image_tag && (
            <span className="text-xs font-mono text-content-muted">
              Current: :{env.current_image_tag}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <div className={cn("w-2 h-2 rounded-full", env.last_deployed_at ? "bg-brand-teal animate-pulse" : "bg-surface-muted")} />
          <span className="text-xs text-content-muted">
            {env.last_deployed_at ? formatRelativeTime(env.last_deployed_at) : "Never deployed"}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2 text-xs text-content-muted mb-4">
        <Server className="w-3 h-3" />
        <span className="font-mono">{env.deploy_path}</span>
        <span className="text-surface-muted">·</span>
        <span className="capitalize">{env.strategy}</span>
      </div>

      {env.health_check_url && (
        <div className="flex items-center gap-1.5 text-xs text-content-muted mb-4">
          <Shield className="w-3 h-3 text-brand-teal" />
          <span className="font-mono truncate">{env.health_check_url}</span>
        </div>
      )}

      <AnimatePresence>
        {showDeploy && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="mb-3 space-y-2 overflow-hidden"
          >
            <input
              value={imageTag}
              onChange={e => setImageTag(e.target.value)}
              placeholder="Image tag (e.g. latest, v1.2.3, sha-abc123)"
              className="input-field text-sm font-mono"
            />
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex gap-2">
        <motion.button
          whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          onClick={() => showDeploy ? deploy.mutate() : setShowDeploy(true)}
          disabled={deploy.isPending}
          className={cn(
            "flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-medium transition-all",
            env.tier === "production"
              ? "border border-brand-crimson/40 text-brand-crimson hover:bg-brand-crimson/10"
              : "btn-primary text-sm"
          )}
        >
          {deploy.isPending ? (
            <><RefreshCw className="w-3 h-3 animate-spin" /> Deploying...</>
          ) : showDeploy ? (
            <><Rocket className="w-3 h-3" /> {env.tier === "production" ? "Deploy to Production" : "Deploy"}</>
          ) : (
            <><Rocket className="w-3 h-3" /> Deploy</>
          )}
        </motion.button>
        {showDeploy && (
          <button
            onClick={() => setShowDeploy(false)}
            className="px-3 py-2 border border-surface-border rounded-lg text-xs text-content-muted hover:border-surface-muted transition-colors"
          >
            Cancel
          </button>
        )}
      </div>
    </motion.div>
  );
}

export default function LaunchControlPage() {
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  const { data: projects } = useQuery({
    queryKey: ["projects", orgId],
    queryFn: () => apiClient.get(`/orgs/${orgId}/projects`).then(r => r.data),
    enabled: !!orgId,
  });

  const { data: deployStats } = useQuery({
    queryKey: ["deploy-stats", orgId],
    queryFn: () => apiClient.get(`/deploy/orgs/${orgId}/deploy-stats`).then(r => r.data),
    enabled: !!orgId,
    refetchInterval: 10000,
  });

  const { data: envData } = useQuery({
    queryKey: ["environments", selectedProjectId],
    queryFn: () => apiClient.get(`/deploy/orgs/${orgId}/projects/${selectedProjectId}/environments`).then(r => r.data),
    enabled: !!orgId && !!selectedProjectId,
  });

  const { data: deployData } = useQuery({
    queryKey: ["deployments", selectedProjectId],
    queryFn: () => apiClient.get(`/deploy/orgs/${orgId}/projects/${selectedProjectId}/deployments`).then(r => r.data),
    enabled: !!orgId && !!selectedProjectId,
    refetchInterval: 5000,
  });

  const projectList = projects?.projects || [];
  const environments = Array.isArray(envData) ? envData : [];
  const deployments = deployData?.deployments || [];
  const selectedProject = projectList.find((p: any) => p.id === selectedProjectId);

  const STATS = [
    { label: "Total Deploys", value: deployStats?.total_deployments || 0, icon: Rocket, color: "text-brand-accent" },
    { label: "Today", value: deployStats?.deployments_today || 0, icon: Play, color: "text-brand-cyan" },
    { label: "Success Rate (7d)", value: deployStats?.success_rate_7d != null ? `${deployStats.success_rate_7d}%` : "—", icon: CheckCircle2, color: "text-brand-teal" },
    { label: "Avg Deploy Time", value: deployStats?.avg_deploy_time_seconds ? `${Math.round(deployStats.avg_deploy_time_seconds)}s` : "—", icon: Clock, color: "text-brand-gold" },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
            <Rocket className="w-7 h-7 text-brand-accent" />
            Launch Control
          </h1>
          <p className="text-content-muted text-sm mt-1">
            Deploy, promote, and roll back across all environments
          </p>
        </div>
        <Link href="/settings/servers">
          <button className="btn-secondary flex items-center gap-2 text-sm">
            <Server className="w-4 h-4" />
            Manage Servers
          </button>
        </Link>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4">
        {STATS.map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
            className="glass-card p-4 text-center"
          >
            <stat.icon className={cn("w-5 h-5 mx-auto mb-2", stat.color)} />
            <div className={cn("text-2xl font-black", stat.color)}>{stat.value}</div>
            <div className="text-xs text-content-muted">{stat.label}</div>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Project selector */}
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-content-secondary uppercase tracking-wider">Projects</h2>
          {projectList.length === 0 ? (
            <div className="glass-card p-6 text-center">
              <p className="text-content-muted text-sm">No projects yet</p>
              <Link href="/projects/new">
                <button className="btn-primary mt-3 text-sm">Create Project</button>
              </Link>
            </div>
          ) : (
            <div className="space-y-2">
              {projectList.map((project: any) => (
                <motion.button
                  key={project.id}
                  whileHover={{ x: 3 }}
                  onClick={() => setSelectedProjectId(project.id)}
                  className={cn(
                    "w-full flex items-center gap-3 p-3 rounded-lg border text-left transition-all",
                    selectedProjectId === project.id
                      ? "border-brand-accent bg-brand-accent/10 shadow-glow-accent"
                      : "border-surface-border hover:border-surface-muted bg-surface-raised"
                  )}
                >
                  <div className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0",
                    selectedProjectId === project.id ? "bg-brand-accent/20 text-brand-accent" : "bg-surface-overlay text-content-muted"
                  )}>
                    {project.name[0].toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-content-primary truncate">{project.name}</p>
                    <p className="text-xs text-content-muted capitalize">{project.project_type}</p>
                  </div>
                  {selectedProjectId === project.id && <ChevronDown className="w-4 h-4 text-brand-accent flex-shrink-0" />}
                </motion.button>
              ))}
            </div>
          )}
        </div>

        {/* Environments + recent deploys */}
        <div className="lg:col-span-2 space-y-4">
          {!selectedProjectId ? (
            <div className="glass-card p-12 text-center">
              <Rocket className="w-10 h-10 text-surface-muted mx-auto mb-3" />
              <p className="text-content-muted">Select a project to view environments</p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-content-secondary uppercase tracking-wider">
                  Environments — {selectedProject?.name}
                </h2>
                <Link href={`/dashboard/environments/new?project=${selectedProjectId}`}>
                  <button className="text-xs text-brand-accent hover:text-brand-cyan transition-colors flex items-center gap-1">
                    <Zap className="w-3 h-3" /> Add Environment
                  </button>
                </Link>
              </div>

              {environments.length === 0 ? (
                <div className="glass-card p-8 text-center">
                  <Server className="w-8 h-8 text-surface-muted mx-auto mb-2" />
                  <p className="text-content-muted text-sm mb-3">No environments configured</p>
                  <p className="text-xs text-content-muted max-w-xs mx-auto">
                    Add a server and create environments to start deploying
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {environments.map((env: any) => (
                    <EnvironmentCard
                      key={env.id}
                      env={env}
                      projectId={selectedProjectId}
                      orgId={orgId}
                    />
                  ))}
                </div>
              )}

              {/* Recent deployments */}
              {deployments.length > 0 && (
                <div className="glass-card overflow-hidden">
                  <div className="px-5 py-3 border-b border-surface-border flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-content-primary">Recent Deployments</h3>
                    <Link href={`/dashboard/deployments?project=${selectedProjectId}`}>
                      <span className="text-xs text-brand-accent hover:text-brand-cyan transition-colors">
                        View all →
                      </span>
                    </Link>
                  </div>
                  {deployments.slice(0, 8).map((dep: any) => (
                    <DeploymentRow key={dep.id} dep={dep} />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
