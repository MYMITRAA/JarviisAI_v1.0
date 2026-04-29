"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import {
  Plus, FolderOpen, Globe, Smartphone, Code2,
  CheckCircle2, XCircle, Clock, Play, GitBranch,
  ArrowRight, Zap
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId, useOrgSlug } from "@/store/auth";
import { cn, formatRelativeTime } from "@/lib/utils";

const PROJECT_TYPE_ICONS: Record<string, any> = {
  web: Globe, android: Smartphone, ios: Smartphone,
  api: Code2, docker: Code2, cobol: Code2,
};

const PROJECT_TYPE_LABELS: Record<string, string> = {
  web: "Web App", android: "Android", ios: "iOS",
  api: "API", docker: "Docker", cobol: "COBOL",
};

const STATUS_CONFIG: Record<string, { icon: any; color: string; label: string }> = {
  passed: { icon: CheckCircle2, color: "text-brand-teal", label: "Passing" },
  failed: { icon: XCircle, color: "text-brand-crimson", label: "Failing" },
  running: { icon: Clock, color: "text-brand-accent", label: "Running" },
};

function ProjectCard({ project }: { project: any }) {
  const Icon = PROJECT_TYPE_ICONS[project.project_type] || Globe;
  const statusCfg = STATUS_CONFIG[project.last_run_status] || null;
  const StatusIcon = statusCfg?.icon;

  return (
    <Link href={`/projects/${project.id}`}>
      <motion.div
        whileHover={{ y: -3, scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
        className="glass-card p-5 glow-border group cursor-pointer h-full"
      >
        <div className="flex items-start justify-between mb-4">
          <div className={cn(
            "w-10 h-10 rounded-lg flex items-center justify-center",
            "bg-brand-accent/10 border border-brand-accent/20 group-hover:border-brand-accent/50 transition-colors"
          )}>
            <Icon className="w-5 h-5 text-brand-accent" />
          </div>
          <div className="flex items-center gap-2">
            <span className="badge badge-purple text-xs">{PROJECT_TYPE_LABELS[project.project_type]}</span>
            {statusCfg && StatusIcon && (
              <StatusIcon className={cn("w-4 h-4", statusCfg.color)} />
            )}
          </div>
        </div>

        <h3 className="font-semibold text-content-primary mb-1 group-hover:text-brand-accent transition-colors">
          {project.name}
        </h3>
        {project.description && (
          <p className="text-xs text-content-muted mb-3 line-clamp-2">{project.description}</p>
        )}

        <div className="flex items-center justify-between text-xs text-content-muted mt-auto pt-3 border-t border-surface-border">
          <span className="flex items-center gap-1.5">
            <Play className="w-3 h-3" />
            {project.total_runs} runs
          </span>
          {project.pass_rate !== null && project.pass_rate !== undefined && (
            <span className={cn(
              "font-medium",
              project.pass_rate >= 80 ? "text-brand-teal" : project.pass_rate >= 50 ? "text-yellow-400" : "text-brand-crimson"
            )}>
              {project.pass_rate}% pass
            </span>
          )}
          {project.last_run_at && (
            <span>{formatRelativeTime(project.last_run_at)}</span>
          )}
        </div>
      </motion.div>
    </Link>
  );
}

export default function ProjectsPage() {
  const { user } = useAuthStore();
  const orgId = useOrgId();

  const { data, isLoading, error } = useQuery({
    queryKey: ["projects", orgId],
    queryFn: () => apiClient.get(`/orgs/${orgId}/projects`).then(r => r.data),
    enabled: !!orgId,
  });

  const projects = data?.projects || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-content-primary">Projects</h1>
          <p className="text-content-muted text-sm mt-1">
            {projects.length} project{projects.length !== 1 ? "s" : ""} — each with autonomous AI testing
          </p>
        </div>
        <Link href="/projects/new">
          <motion.button
            whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
            className="btn-primary flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            New Project
          </motion.button>
        </Link>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="glass-card p-5 animate-pulse">
              <div className="w-10 h-10 bg-surface-border rounded-lg mb-4" />
              <div className="h-4 bg-surface-border rounded mb-2 w-3/4" />
              <div className="h-3 bg-surface-border rounded w-1/2" />
            </div>
          ))}
        </div>
      )}

      {/* Projects grid */}
      {!isLoading && projects.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project: any, i: number) => (
            <motion.div
              key={project.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06 }}
            >
              <ProjectCard project={project} />
            </motion.div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && projects.length === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card p-12 text-center"
        >
          <div className="flex justify-center mb-5">
            <motion.div
              animate={{ y: [0, -10, 0] }}
              transition={{ duration: 2, repeat: Infinity }}
              className="w-16 h-16 rounded-2xl bg-brand-accent/10 border border-brand-accent/30 flex items-center justify-center"
            >
              <FolderOpen className="w-8 h-8 text-brand-accent" />
            </motion.div>
          </div>
          <h3 className="text-xl font-bold text-content-primary mb-2">No projects yet</h3>
          <p className="text-content-muted text-sm mb-6 max-w-md mx-auto">
            Create your first project and JarviisAI will autonomously crawl your app,
            generate tests, and start protecting your quality.
          </p>
          <Link href="/projects/new">
            <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} className="btn-primary">
              <span className="flex items-center gap-2">
                <Zap className="w-4 h-4" />
                Create First Project
                <ArrowRight className="w-4 h-4" />
              </span>
            </motion.button>
          </Link>
        </motion.div>
      )}
    </div>
  );
}
