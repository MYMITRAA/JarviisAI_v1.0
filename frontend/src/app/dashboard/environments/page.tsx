"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowRight, CheckCircle2, Rocket, Shield, AlertCircle,
  Zap, GitBranch
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId, useOrgSlug } from "@/store/auth";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const TIER_ORDER = ["development", "staging", "production"];

const TIER_STYLE: Record<string, { color: string; bg: string; border: string }> = {
  development: { color: "text-brand-cyan",    bg: "bg-brand-cyan/10",    border: "border-brand-cyan/30" },
  staging:     { color: "text-brand-gold",    bg: "bg-brand-gold/10",    border: "border-brand-gold/30" },
  production:  { color: "text-brand-crimson", bg: "bg-brand-crimson/10", border: "border-brand-crimson/30" },
  custom:      { color: "text-content-muted", bg: "bg-surface-border",   border: "border-surface-border" },
};

export default function EnvironmentsPage() {
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const qc = useQueryClient();
  const [promotingFrom, setPromotingFrom] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);

  const { data: projects } = useQuery({
    queryKey: ["projects", orgId],
    queryFn: () => apiClient.get(`/orgs/${orgId}/projects`).then(r => r.data),
    enabled: !!orgId,
  });

  const { data: envData } = useQuery({
    queryKey: ["environments", selectedProject],
    queryFn: () => apiClient.get(`/deploy/orgs/${orgId}/projects/${selectedProject}/environments`).then(r => r.data),
    enabled: !!orgId && !!selectedProject,
  });

  const promote = useMutation({
    mutationFn: (data: { from_id: string; to_id: string }) =>
      apiClient.post(`/deploy/orgs/${orgId}/projects/${selectedProject}/promote`, {
        from_environment_id: data.from_id,
        to_environment_id: data.to_id,
        run_tests_first: true,
      }),
    onSuccess: (res) => {
      toast.success(`Promotion to ${res.data.to_tier} started!`);
      setPromotingFrom(null);
      qc.invalidateQueries({ queryKey: ["environments"] });
      qc.invalidateQueries({ queryKey: ["deployments"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Promotion failed"),
  });

  const projectList = projects?.projects || [];
  const environments = Array.isArray(envData) ? envData : [];

  // Sort envs by tier order
  const sortedEnvs = [...environments].sort(
    (a: any, b: any) => TIER_ORDER.indexOf(a.tier) - TIER_ORDER.indexOf(b.tier)
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-content-primary">Environments</h1>
        <p className="text-content-muted text-sm mt-1">
          Promote builds through dev → staging → production with one click
        </p>
      </div>

      {/* Project selector */}
      <div className="flex items-center gap-2 flex-wrap">
        {projectList.map((p: any) => (
          <button
            key={p.id}
            onClick={() => setSelectedProject(p.id)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
              selectedProject === p.id
                ? "bg-brand-accent/15 text-brand-accent border border-brand-accent/30"
                : "border border-surface-border text-content-muted hover:border-surface-muted"
            )}
          >
            {p.name}
          </button>
        ))}
      </div>

      {!selectedProject ? (
        <div className="glass-card p-12 text-center">
          <Rocket className="w-10 h-10 text-surface-muted mx-auto mb-3" />
          <p className="text-content-muted">Select a project to view its environments</p>
        </div>
      ) : sortedEnvs.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <p className="text-content-muted text-sm">No environments configured for this project</p>
          <p className="text-xs text-content-muted mt-1">
            Add environments from the Deploy → Launch Control page
          </p>
        </div>
      ) : (
        /* Environment promotion pipeline */
        <div className="relative">
          <div className="flex items-stretch gap-0">
            {sortedEnvs.map((env: any, idx: number) => {
              const style = TIER_STYLE[env.tier] || TIER_STYLE.custom;
              const nextEnv = sortedEnvs[idx + 1];
              const isPromoting = promotingFrom === env.id;

              return (
                <div key={env.id} className="flex items-center gap-0 flex-1">
                  {/* Environment card */}
                  <motion.div
                    whileHover={{ y: -2 }}
                    className={cn("flex-1 glass-card p-5 border-2 transition-all duration-200", style.border)}
                  >
                    <div className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold mb-3", style.bg, style.color)}>
                      <span className="capitalize">{env.tier}</span>
                    </div>

                    <h3 className="font-semibold text-content-primary mb-1">{env.name}</h3>

                    {env.current_image_tag ? (
                      <p className="text-xs font-mono text-content-muted mb-2">
                        :{env.current_image_tag}
                      </p>
                    ) : (
                      <p className="text-xs text-content-muted mb-2 italic">Not deployed</p>
                    )}

                    <div className="flex items-center gap-2 text-xs text-content-muted">
                      <Shield className="w-3 h-3" />
                      <span>{env.health_check_url ? "Health check configured" : "No health check"}</span>
                    </div>

                    {env.auto_deploy_branch && (
                      <div className="flex items-center gap-2 text-xs text-brand-cyan mt-1.5">
                        <GitBranch className="w-3 h-3" />
                        <span>Auto-deploy: {env.auto_deploy_branch}</span>
                      </div>
                    )}

                    {/* Promote button (only from this env, if there's a next) */}
                    {nextEnv && (
                      <div className="mt-4 pt-3 border-t border-surface-border">
                        {!isPromoting ? (
                          <button
                            onClick={() => setPromotingFrom(env.id)}
                            className={cn(
                              "w-full flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-medium border transition-all",
                              nextEnv.tier === "production"
                                ? "border-brand-crimson/40 text-brand-crimson hover:bg-brand-crimson/10"
                                : "border-brand-accent/40 text-brand-accent hover:bg-brand-accent/10"
                            )}
                          >
                            Promote to {nextEnv.tier}
                            <ArrowRight className="w-3 h-3" />
                          </button>
                        ) : (
                          <div className="space-y-2">
                            {nextEnv.tier === "production" && (
                              <div className="flex items-start gap-2 p-2 bg-brand-crimson/5 border border-brand-crimson/20 rounded text-xs text-brand-crimson">
                                <AlertCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                                <span>This will promote to <strong>production</strong>. Are you sure?</span>
                              </div>
                            )}
                            <div className="flex gap-2">
                              <button
                                onClick={() => promote.mutate({ from_id: env.id, to_id: nextEnv.id })}
                                disabled={promote.isPending}
                                className={cn(
                                  "flex-1 py-1.5 rounded-lg text-xs font-medium transition-all",
                                  nextEnv.tier === "production"
                                    ? "bg-brand-crimson text-white hover:bg-brand-crimson/80"
                                    : "bg-brand-accent text-white hover:bg-brand-accent/80"
                                )}
                              >
                                {promote.isPending ? "Promoting..." : "Confirm"}
                              </button>
                              <button
                                onClick={() => setPromotingFrom(null)}
                                className="px-3 py-1.5 border border-surface-border rounded-lg text-xs text-content-muted hover:border-surface-muted"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </motion.div>

                  {/* Arrow connector */}
                  {idx < sortedEnvs.length - 1 && (
                    <div className="flex-shrink-0 flex flex-col items-center px-2">
                      <ArrowRight className="w-5 h-5 text-surface-muted" />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="glass-card p-4">
        <p className="text-xs font-semibold text-content-muted mb-3 uppercase tracking-wider">Promotion Rules</p>
        <div className="grid grid-cols-3 gap-3 text-xs text-content-secondary">
          <div className="flex items-start gap-2">
            <CheckCircle2 className="w-3.5 h-3.5 text-brand-teal mt-0.5 flex-shrink-0" />
            <span>Tests must pass before promotion (configurable)</span>
          </div>
          <div className="flex items-start gap-2">
            <Zap className="w-3.5 h-3.5 text-brand-accent mt-0.5 flex-shrink-0" />
            <span>Same image tag is promoted — no rebuild</span>
          </div>
          <div className="flex items-start gap-2">
            <Shield className="w-3.5 h-3.5 text-brand-gold mt-0.5 flex-shrink-0" />
            <span>Health check runs after every deployment</span>
          </div>
        </div>
      </div>
    </div>
  );
}
