"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Server, Users, Building2, CreditCard, Activity,
  CheckCircle2, XCircle, AlertCircle, RefreshCw,
  Zap, Database, BarChart3, Settings2
} from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { cn, formatRelativeTime } from "@/lib/utils";
import Link from "next/link";

const SERVICES = [
  { name: "Auth",          port: 8001, key: "auth" },
  { name: "Projects",      port: 8002, key: "projects" },
  { name: "Crawler",       port: 8003, key: "crawler" },
  { name: "AI Orchestrator",port:8004, key: "ai" },
  { name: "Test Executor", port: 8005, key: "executor" },
  { name: "Healing",       port: 8006, key: "healing" },
  { name: "Visual",        port: 8007, key: "visual" },
  { name: "Deploy",        port: 8008, key: "deploy" },
  { name: "API Tester",    port: 8009, key: "api-tester" },
  { name: "Security",      port: 8011, key: "security" },
  { name: "Jarviis AI",    port: 8012, key: "jarviis-ai" },
  { name: "COBOL",         port: 8013, key: "cobol" },
  { name: "Billing",       port: 8014, key: "billing" },
  { name: "SSO",           port: 8015, key: "sso" },
  { name: "Mobile",        port: 8016, key: "mobile" },
];

function ServiceHealthCard({ service }: { service: typeof SERVICES[0] }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["health", service.key],
    queryFn: () => fetch(`http://localhost:${service.port}/health`).then(r => r.json()),
    refetchInterval: 30000,
    retry: 1,
  });

  const healthy = !error && !isLoading && data?.status === "ok";
  const degraded = !error && !isLoading && data?.status !== "ok";
  const down = !!error;

  return (
    <div className={cn(
      "flex items-center gap-3 px-4 py-3 rounded-lg border transition-all",
      healthy ? "border-brand-teal/20 bg-brand-teal/5" :
      degraded ? "border-brand-gold/20 bg-brand-gold/5" :
      down ? "border-brand-crimson/20 bg-brand-crimson/5" :
      "border-surface-border bg-surface-overlay"
    )}>
      {isLoading ? (
        <RefreshCw className="w-3.5 h-3.5 text-content-muted animate-spin" />
      ) : healthy ? (
        <CheckCircle2 className="w-3.5 h-3.5 text-brand-teal" />
      ) : degraded ? (
        <AlertCircle className="w-3.5 h-3.5 text-brand-gold" />
      ) : (
        <XCircle className="w-3.5 h-3.5 text-brand-crimson" />
      )}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-content-primary">{service.name}</p>
        <p className="text-xs text-content-muted font-mono">:{service.port}</p>
      </div>
      {data?.ai_configured === false && (
        <span className="text-xs text-brand-gold">No AI</span>
      )}
    </div>
  );
}

export default function AdminPage() {
  const qc = useQueryClient();

  // Mock admin stats
  const stats = [
    { label: "Total Organizations", value: "—", icon: Building2, href: "/admin/orgs" },
    { label: "Total Users", value: "—", icon: Users, href: "/admin/users" },
    { label: "Active Subscriptions", value: "—", icon: CreditCard, href: "/admin/billing" },
    { label: "Test Runs Today", value: "—", icon: Activity, href: "/dashboard" },
  ];

  const ADMIN_SECTIONS = [
    { href: "/admin/users", icon: Users, label: "Users", desc: "Manage user accounts, roles, and permissions" },
    { href: "/admin/orgs", icon: Building2, label: "Organizations", desc: "View and manage organization subscriptions" },
    { href: "/admin/billing", icon: CreditCard, label: "Billing", desc: "Revenue overview, invoices, and plan management" },
    { href: "/admin/system", icon: Settings2, label: "System", desc: "Feature flags, maintenance mode, and config" },
  ];

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <Server className="w-6 h-6 text-brand-accent" />
          Admin Panel
        </h1>
        <p className="text-content-muted text-sm mt-1">System overview and administration</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, i) => (
          <motion.div key={stat.label} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
            <Link href={stat.href}>
              <div className="glass-card p-4 hover:border-brand-accent/40 transition-all cursor-pointer text-center">
                <stat.icon className="w-5 h-5 text-brand-accent mx-auto mb-2" />
                <div className="text-2xl font-black text-content-primary">{stat.value}</div>
                <div className="text-xs text-content-muted">{stat.label}</div>
              </div>
            </Link>
          </motion.div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Service health */}
        <div className="glass-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-content-primary flex items-center gap-2">
              <Activity className="w-4 h-4 text-brand-teal" />
              Service Health
            </h2>
            <button
              onClick={() => qc.invalidateQueries({ queryKey: ["health"] })}
              className="text-xs text-brand-accent hover:text-brand-cyan transition-colors flex items-center gap-1"
            >
              <RefreshCw className="w-3 h-3" /> Refresh
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {SERVICES.map(svc => (
              <ServiceHealthCard key={svc.key} service={svc} />
            ))}
          </div>
        </div>

        {/* Admin sections */}
        <div className="space-y-3">
          <h2 className="font-semibold text-content-primary">Administration</h2>
          {ADMIN_SECTIONS.map(section => (
            <Link key={section.href} href={section.href}>
              <motion.div
                whileHover={{ x: 4 }}
                className="glass-card p-4 flex items-center gap-4 cursor-pointer hover:border-brand-accent/40 transition-all"
              >
                <div className="w-10 h-10 rounded-lg bg-brand-accent/10 border border-brand-accent/20 flex items-center justify-center flex-shrink-0">
                  <section.icon className="w-5 h-5 text-brand-accent" />
                </div>
                <div>
                  <p className="font-semibold text-content-primary text-sm">{section.label}</p>
                  <p className="text-xs text-content-muted">{section.desc}</p>
                </div>
              </motion.div>
            </Link>
          ))}

          {/* Observability links */}
          <div className="glass-card p-4">
            <h3 className="text-sm font-semibold text-content-secondary mb-3 flex items-center gap-2">
              <BarChart3 className="w-4 h-4" /> Observability
            </h3>
            <div className="space-y-2">
              {[
                { label: "Grafana Dashboards", url: "http://localhost:3001", desc: "Metrics & dashboards" },
                { label: "Prometheus", url: "http://localhost:9090", desc: "Raw metrics & queries" },
                { label: "Jaeger Traces", url: "http://localhost:16686", desc: "Distributed tracing" },
              ].map(link => (
                <a key={link.url} href={link.url} target="_blank" rel="noopener noreferrer"
                   className="flex items-center justify-between p-2 rounded-lg hover:bg-surface-overlay transition-colors group">
                  <div>
                    <span className="text-xs font-medium text-content-primary group-hover:text-brand-accent transition-colors">
                      {link.label}
                    </span>
                    <p className="text-xs text-content-muted">{link.desc}</p>
                  </div>
                  <span className="text-xs font-mono text-content-muted">{link.url.split("//")[1]}</span>
                </a>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
