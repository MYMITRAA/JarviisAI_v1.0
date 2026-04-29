"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";
import { Globe, Smartphone, Code2, ArrowLeft, ArrowRight, Zap, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId, useOrgSlug } from "@/store/auth";
import { cn, slugify } from "@/lib/utils";

const schema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  slug: z.string().min(2).max(80).regex(/^[a-z0-9-]+$/, "Lowercase letters, numbers, and hyphens only"),
  project_type: z.enum(["web", "android", "ios", "api", "docker", "cobol"]),
  project_url: z.string().url("Enter a valid URL").optional().or(z.literal("")),
  description: z.string().optional(),
});
type FormData = z.infer<typeof schema>;

const PROJECT_TYPES = [
  { value: "web", label: "Web App", icon: Globe, desc: "React, Vue, Angular, plain HTML" },
  { value: "api", label: "REST / GraphQL API", icon: Code2, desc: "OpenAPI, Postman collection" },
  { value: "android", label: "Android App", icon: Smartphone, desc: "APK file upload" },
  { value: "ios", label: "iOS App", icon: Smartphone, desc: "IPA or TestFlight link" },
  { value: "docker", label: "Docker App", icon: Code2, desc: "docker-compose.yml" },
];

export default function NewProjectPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const [isLoading, setIsLoading] = useState(false);

  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { project_type: "web" },
  });

  const selectedType = watch("project_type");
  const projectName = watch("name", "");

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValue("name", e.target.value);
    setValue("slug", slugify(e.target.value), { shouldValidate: true });
  };

  const onSubmit = async (data: FormData) => {
    if (!orgId) { toast.error("No organization found"); return; }
    setIsLoading(true);
    try {
      const res = await apiClient.post(`/orgs/${orgId}/projects`, {
        name: data.name,
        slug: data.slug,
        project_type: data.project_type,
        project_url: data.project_url || null,
        description: data.description || null,
      });
      toast.success(`Project "${data.name}" created! Starting autonomous setup...`);
      router.push(`/projects/${res.data.id}`);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to create project");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      {/* Back */}
      <button onClick={() => router.back()} className="flex items-center gap-2 text-content-muted hover:text-content-primary transition-colors mb-6 text-sm">
        <ArrowLeft className="w-4 h-4" />
        Back to Projects
      </button>

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-8">
        <div className="flex items-center gap-3 mb-7">
          <div className="w-10 h-10 rounded-lg bg-brand-accent/10 border border-brand-accent/30 flex items-center justify-center">
            <Zap className="w-5 h-5 text-brand-accent" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-content-primary">New Project</h1>
            <p className="text-content-muted text-sm">JarviisAI will autonomously test this application</p>
          </div>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {/* Project type */}
          <div>
            <label className="block text-sm font-medium text-content-secondary mb-2">Project Type</label>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {PROJECT_TYPES.map(({ value, label, icon: Icon, desc }) => {
                const sel = selectedType === value;
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setValue("project_type", value as any)}
                    className={cn(
                      "p-3 rounded-lg border text-left transition-all duration-150",
                      sel ? "border-brand-accent bg-brand-accent/10 shadow-glow-accent" : "border-surface-border hover:border-surface-muted"
                    )}
                  >
                    <Icon className={cn("w-4 h-4 mb-1.5", sel ? "text-brand-accent" : "text-content-muted")} />
                    <div className="text-xs font-semibold text-content-primary">{label}</div>
                    <div className="text-xs text-content-muted mt-0.5">{desc}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Project name */}
          <div>
            <label className="block text-sm font-medium text-content-secondary mb-1.5">Project Name</label>
            <input
              {...register("name")}
              onChange={handleNameChange}
              placeholder="My Awesome App"
              className="input-field"
            />
            {errors.name && <p className="text-brand-crimson text-xs mt-1">{errors.name.message}</p>}
          </div>

          {/* Slug */}
          <div>
            <label className="block text-sm font-medium text-content-secondary mb-1.5">Project Slug</label>
            <div className="flex items-center gap-0">
              <span className="px-3 py-3 bg-surface-border text-content-muted text-sm rounded-l-lg border border-r-0 border-surface-border font-mono text-xs">
                projects/
              </span>
              <input {...register("slug")} placeholder="my-awesome-app" className="input-field rounded-l-none font-mono text-sm" />
            </div>
            {errors.slug && <p className="text-brand-crimson text-xs mt-1">{errors.slug.message}</p>}
          </div>

          {/* URL (web/api only) */}
          {(selectedType === "web" || selectedType === "api") && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
              <label className="block text-sm font-medium text-content-secondary mb-1.5">
                {selectedType === "web" ? "Application URL" : "API Base URL"}
              </label>
              <input
                {...register("project_url")}
                type="url"
                placeholder={selectedType === "web" ? "https://myapp.com" : "https://api.myapp.com"}
                className="input-field font-mono text-sm"
              />
              {errors.project_url && <p className="text-brand-crimson text-xs mt-1">{errors.project_url.message}</p>}
              <p className="text-content-muted text-xs mt-1">
                JarviisAI will crawl this URL to discover your application's structure
              </p>
            </motion.div>
          )}

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-content-secondary mb-1.5">Description <span className="text-content-muted">(optional)</span></label>
            <textarea
              {...register("description")}
              rows={2}
              placeholder="What does this application do?"
              className="input-field resize-none"
            />
          </div>

          {/* What happens next */}
          <div className="bg-brand-accent/5 border border-brand-accent/20 rounded-lg p-4">
            <p className="text-xs font-semibold text-brand-accent mb-2">What happens after you create this project:</p>
            <div className="space-y-1.5">
              {[
                "JarviisAI crawls your application with Playwright",
                "Claude AI generates a complete test suite",
                "Tests execute automatically — results in your dashboard",
              ].map((step, i) => (
                <div key={i} className="flex items-center gap-2 text-xs text-content-secondary">
                  <CheckCircle2 className="w-3.5 h-3.5 text-brand-teal flex-shrink-0" />
                  {step}
                </div>
              ))}
            </div>
          </div>

          <motion.button
            whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
            type="submit" disabled={isLoading}
            className="btn-primary w-full"
          >
            {isLoading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Creating project...
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                Create Project <ArrowRight className="w-4 h-4" />
              </span>
            )}
          </motion.button>
        </form>
      </motion.div>
    </div>
  );
}
