"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ClipboardList, Download, Filter, ChevronDown } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId } from "@/store/auth";
import { cn, formatRelativeTime } from "@/lib/utils";
import { FilterBar, FilterState } from "@/components/filters/FilterBar";
import { toast } from "sonner";

const EVENT_BADGES: Record<string, { label: string; color: string }> = {
  "test.started":          { label: "Test Started",   color: "text-brand-cyan bg-brand-cyan/10 border-brand-cyan/20" },
  "test.completed":        { label: "Test Passed",    color: "text-brand-teal bg-brand-teal/10 border-brand-teal/20" },
  "test.failed":           { label: "Test Failed",    color: "text-brand-crimson bg-brand-crimson/10 border-brand-crimson/20" },
  "deploy.started":        { label: "Deploy Started", color: "text-brand-accent bg-brand-accent/10 border-brand-accent/20" },
  "deploy.completed":      { label: "Deployed",       color: "text-brand-teal bg-brand-teal/10 border-brand-teal/20" },
  "deploy.rolled_back":    { label: "Rolled Back",    color: "text-brand-gold bg-brand-gold/10 border-brand-gold/20" },
  "deploy.failed":         { label: "Deploy Failed",  color: "text-brand-crimson bg-brand-crimson/10 border-brand-crimson/20" },
  "billing.plan_changed":  { label: "Plan Changed",   color: "text-brand-accent bg-brand-accent/10 border-brand-accent/20" },
  "billing.trial_started": { label: "Trial Started",  color: "text-brand-cyan bg-brand-cyan/10 border-brand-cyan/20" },
  "org.member_added":      { label: "Member Added",   color: "text-brand-teal bg-brand-teal/10 border-brand-teal/20" },
  "org.member_removed":    { label: "Member Removed", color: "text-brand-gold bg-brand-gold/10 border-brand-gold/20" },
  "sso.login_success":     { label: "SSO Login",      color: "text-brand-cyan bg-brand-cyan/10 border-brand-cyan/20" },
  "healing.applied":       { label: "Healed",         color: "text-brand-gold bg-brand-gold/10 border-brand-gold/20" },
};

export default function AuditLogPage() {
  const orgId = useOrgId();
  const [filters, setFilters] = useState<FilterState>({});
  const [days, setDays] = useState(30);

  const { data, isLoading } = useQuery({
    queryKey: ["audit-log", orgId, days, filters.dateFrom, filters.dateTo],
    queryFn: () => apiClient.get(`/audit/${orgId}?days=${days}&limit=200`).then(r => r.data),
    enabled: !!orgId,
    refetchInterval: 30_000,
  });

  const handleExport = async () => {
    try {
      const response = await apiClient.get(`/audit/${orgId}/export?days=${days}`, { responseType: "blob" });
      const url = URL.createObjectURL(response.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit_log_${orgId}_${days}d.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Audit log exported");
    } catch {
      toast.error("Export failed");
    }
  };

  let entries = data?.entries || [];

  // Apply client-side filters
  if (filters.dateFrom) entries = entries.filter((e: any) => e.timestamp >= filters.dateFrom!);
  if (filters.dateTo)   entries = entries.filter((e: any) => e.timestamp <= filters.dateTo! + "T23:59:59");

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
            <ClipboardList className="w-7 h-7 text-brand-accent" />
            Audit Log
          </h1>
          <p className="text-content-muted text-sm mt-1">
            Immutable record of all actions, changes, and events in your organization
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={days} onChange={e => setDays(Number(e.target.value))} className="input-field text-sm w-36">
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 border border-surface-border rounded-lg text-sm text-content-muted hover:text-brand-accent hover:border-brand-accent/40 transition-all">
            <Download className="w-4 h-4" /> Export JSON
          </motion.button>
        </div>
      </div>

      <FilterBar
        filters={filters}
        onChange={setFilters}
        availableFilters={["date"]}
      />

      <div className="glass-card overflow-hidden">
        <div className="px-5 py-3 border-b border-surface-border flex items-center justify-between">
          <h2 className="font-semibold text-content-primary">{entries.length} Events</h2>
          <span className="text-xs text-content-muted">Most recent first</span>
        </div>

        {isLoading ? (
          <div className="p-6 space-y-3">
            {[1,2,3,4,5].map(i => (
              <div key={i} className="flex items-center gap-4 animate-pulse">
                <div className="w-24 h-5 bg-surface-border rounded" />
                <div className="flex-1 h-4 bg-surface-border rounded" />
                <div className="w-20 h-4 bg-surface-border rounded" />
              </div>
            ))}
          </div>
        ) : entries.length === 0 ? (
          <div className="py-12 text-center">
            <ClipboardList className="w-10 h-10 text-surface-muted mx-auto mb-3" />
            <p className="text-content-muted">No audit events found for the selected period</p>
          </div>
        ) : (
          <div className="divide-y divide-surface-border">
            {entries.map((entry: any, i: number) => {
              const badge = EVENT_BADGES[entry.event] || { label: entry.event, color: "text-content-muted bg-surface-border border-surface-border" };
              const payload = typeof entry.payload === "string" ? JSON.parse(entry.payload || "{}") : entry.payload || {};

              return (
                <motion.div key={entry.id || i} whileHover={{ x: 2 }}
                  className="flex items-center gap-4 px-5 py-3 hover:bg-surface-overlay transition-all">
                  <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium whitespace-nowrap flex-shrink-0 min-w-[100px] text-center", badge.color)}>
                    {badge.label}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-content-secondary truncate">
                      {entry.actor_id && <span className="text-brand-cyan font-mono">{entry.actor_id.slice(0, 8)}···</span>}
                      {" · "}
                      {entry.source || "system"}
                      {Object.keys(payload).length > 0 && (
                        <span className="text-content-muted"> · {Object.entries(payload).slice(0, 2).map(([k, v]) => `${k}=${String(v).slice(0, 20)}`).join(", ")}</span>
                      )}
                    </p>
                  </div>
                  <span className="text-xs text-content-muted flex-shrink-0">
                    {formatRelativeTime(entry.timestamp)}
                  </span>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
