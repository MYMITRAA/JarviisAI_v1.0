"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Github, Save, Trash2, Globe, AlertCircle } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId, useOrgSlug } from "@/store/auth";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export default function ProjectSettingsPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const qc = useQueryClient();

  const [projectUrl, setProjectUrl] = useState("");
  const [repoFullName, setRepoFullName] = useState("");
  const [triggerOnPush, setTriggerOnPush] = useState(true);
  const [triggerOnPr, setTriggerOnPr] = useState(true);
  const [defaultBranch, setDefaultBranch] = useState("main");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const { data: project, isLoading } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => apiClient.get(`/orgs/${orgId}/projects/${projectId}`).then(r => {
      const d = r.data;
      setProjectUrl(d.project_url || "");
      return d;
    }),
    enabled: !!orgId && !!projectId,
  });

  const updateProject = useMutation({
    mutationFn: (data: any) => apiClient.patch(`/orgs/${orgId}/projects/${projectId}`, data),
    onSuccess: () => {
      toast.success("Project settings saved");
      qc.invalidateQueries({ queryKey: ["project", projectId] });
    },
    onError: () => toast.error("Failed to save settings"),
  });

  const connectGitHub = useMutation({
    mutationFn: () => apiClient.post(`/orgs/${orgId}/projects/${projectId}/github`, {
      repo_full_name: repoFullName,
      default_branch: defaultBranch,
      trigger_on_push: triggerOnPush,
      trigger_on_pr: triggerOnPr,
    }),
    onSuccess: () => toast.success("GitHub connected!"),
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Failed to connect GitHub"),
  });

  const deleteProject = useMutation({
    mutationFn: () => apiClient.delete(`/orgs/${orgId}/projects/${projectId}`),
    onSuccess: () => {
      toast.success("Project deleted");
      router.push("/projects");
    },
    onError: () => toast.error("Failed to delete project"),
  });

  if (isLoading || !project) return <div className="flex items-center justify-center h-48"><div className="w-6 h-6 border-2 border-brand-accent border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="max-w-2xl space-y-6">
      <button onClick={() => router.push(`/projects/${projectId}`)} className="flex items-center gap-2 text-content-muted hover:text-content-primary transition-colors text-sm">
        <ArrowLeft className="w-4 h-4" /> Back to {project.name}
      </button>

      <h1 className="text-xl font-black text-content-primary">Project Settings</h1>

      {/* General settings */}
      <div className="glass-card p-6 space-y-4">
        <h2 className="font-semibold text-content-primary flex items-center gap-2">
          <Globe className="w-4 h-4 text-brand-accent" /> General
        </h2>
        <div>
          <label className="block text-sm font-medium text-content-secondary mb-1.5">Application URL</label>
          <input
            value={projectUrl}
            onChange={e => setProjectUrl(e.target.value)}
            placeholder="https://myapp.com"
            className="input-field font-mono text-sm"
          />
          <p className="text-xs text-content-muted mt-1">JarviisAI will crawl this URL to discover and test your application</p>
        </div>
        <motion.button
          whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
          onClick={() => updateProject.mutate({ project_url: projectUrl })}
          disabled={updateProject.isPending}
          className="btn-primary flex items-center gap-2"
        >
          <Save className="w-4 h-4" />
          {updateProject.isPending ? "Saving..." : "Save Changes"}
        </motion.button>
      </div>

      {/* GitHub integration */}
      <div className="glass-card p-6 space-y-4">
        <h2 className="font-semibold text-content-primary flex items-center gap-2">
          <Github className="w-4 h-4" /> GitHub Integration
        </h2>
        <div>
          <label className="block text-sm font-medium text-content-secondary mb-1.5">Repository</label>
          <input
            value={repoFullName}
            onChange={e => setRepoFullName(e.target.value)}
            placeholder="owner/repository"
            className="input-field font-mono text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-content-secondary mb-1.5">Default Branch</label>
          <input
            value={defaultBranch}
            onChange={e => setDefaultBranch(e.target.value)}
            placeholder="main"
            className="input-field font-mono text-sm"
          />
        </div>
        <div className="flex items-center gap-6">
          {[
            { label: "Trigger on push", value: triggerOnPush, set: setTriggerOnPush },
            { label: "Trigger on PR", value: triggerOnPr, set: setTriggerOnPr },
          ].map(({ label, value, set }) => (
            <label key={label} className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={value} onChange={e => set(e.target.checked)}
                     className="w-4 h-4 accent-brand-accent" />
              <span className="text-sm text-content-secondary">{label}</span>
            </label>
          ))}
        </div>
        <motion.button
          whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
          onClick={() => connectGitHub.mutate()}
          disabled={connectGitHub.isPending || !repoFullName}
          className="btn-primary flex items-center gap-2"
        >
          <Github className="w-4 h-4" />
          {connectGitHub.isPending ? "Connecting..." : "Connect GitHub"}
        </motion.button>
        <p className="text-xs text-content-muted">
          Webhook URL: <code className="font-mono bg-surface-border px-1.5 py-0.5 rounded text-brand-neon text-xs">
            {process.env.NEXT_PUBLIC_API_URL}/api/v1/webhooks/github
          </code>
        </p>
      </div>

      {/* Danger zone */}
      <div className="glass-card p-6 border-brand-crimson/20 space-y-4">
        <h2 className="font-semibold text-brand-crimson flex items-center gap-2">
          <AlertCircle className="w-4 h-4" /> Danger Zone
        </h2>
        {!confirmDelete ? (
          <button
            onClick={() => setConfirmDelete(true)}
            className="flex items-center gap-2 px-4 py-2 border border-brand-crimson/30 text-brand-crimson rounded-lg text-sm hover:bg-brand-crimson/10 transition-colors"
          >
            <Trash2 className="w-4 h-4" /> Delete Project
          </button>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-brand-crimson">Are you sure? This will permanently delete all runs, test cases, and settings.</p>
            <div className="flex gap-3">
              <button onClick={() => deleteProject.mutate()}
                      className="px-4 py-2 bg-brand-crimson text-white rounded-lg text-sm font-medium hover:bg-brand-crimson/80 transition-colors">
                {deleteProject.isPending ? "Deleting..." : "Yes, delete permanently"}
              </button>
              <button onClick={() => setConfirmDelete(false)}
                      className="px-4 py-2 border border-surface-border text-content-muted rounded-lg text-sm hover:border-surface-muted transition-colors">
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
