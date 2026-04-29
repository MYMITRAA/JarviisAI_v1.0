"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Building2, Search, TrendingUp, TrendingDown, Users, RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { cn, formatRelativeTime } from "@/lib/utils";

export default function AdminOrgsPage() {
  const [search, setSearch] = useState("");

  const { data: healthData, isLoading } = useQuery({
    queryKey: ["admin-health-scores"],
    queryFn: () => apiClient.get(`/health-score/admin/all`).then(r => r.data),
    staleTime: 60_000,
  });

  const orgs = healthData?.scores || [];
  const filtered = search
    ? orgs.filter((o: any) => o.org_id?.includes(search))
    : orgs;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <Building2 className="w-7 h-7 text-brand-accent" />
          Organizations
        </h1>
        <p className="text-content-muted text-sm mt-1">Health scores and activity across all orgs</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Total Orgs",     value: orgs.length,                                           color: "text-brand-accent" },
          { label: "Churn Risk",     value: orgs.filter((o: any) => o.risk === "churn_risk").length, color: "text-brand-crimson" },
          { label: "Expansion Opps", value: orgs.filter((o: any) => o.risk === "expansion").length, color: "text-brand-teal" },
        ].map(({ label, value, color }) => (
          <div key={label} className="glass-card p-4 text-center">
            <div className={cn("text-2xl font-black", color)}>{value}</div>
            <div className="text-xs text-content-muted">{label}</div>
          </div>
        ))}
      </div>

      <div className="glass-card overflow-hidden">
        <div className="px-5 py-3 border-b border-surface-border flex items-center gap-3">
          <Search className="w-4 h-4 text-content-muted" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Filter by org ID..." className="bg-transparent text-sm outline-none flex-1" />
        </div>

        {isLoading ? (
          <div className="p-6 space-y-3">
            {[1,2,3].map(i => <div key={i} className="h-12 bg-surface-border rounded animate-pulse" />)}
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center">
            <Building2 className="w-10 h-10 text-surface-muted mx-auto mb-3" />
            <p className="text-content-muted text-sm">No orgs with health scores yet</p>
            <p className="text-xs text-content-muted mt-1">Scores appear after orgs run their first test</p>
          </div>
        ) : (
          <div className="divide-y divide-surface-border">
            {filtered.map((org: any) => (
              <div key={org.org_id} className="flex items-center gap-4 px-5 py-3.5 hover:bg-surface-overlay transition-colors">
                <div className={cn(
                  "w-10 h-10 rounded-xl flex items-center justify-center text-lg font-black flex-shrink-0",
                  org.score >= 75 ? "bg-brand-teal/10 text-brand-teal" :
                  org.score >= 40 ? "bg-brand-gold/10 text-brand-gold" :
                  "bg-brand-crimson/10 text-brand-crimson"
                )}>
                  {org.score}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-content-primary font-mono truncate">{org.org_id}</p>
                  <p className="text-xs text-content-muted capitalize">{org.risk?.replace("_", " ")}</p>
                </div>
                <div className="flex items-center gap-2">
                  {org.risk === "churn_risk" && (
                    <span className="text-xs px-2 py-0.5 bg-brand-crimson/10 text-brand-crimson rounded-full border border-brand-crimson/20">
                      ⚠ Churn Risk
                    </span>
                  )}
                  {org.risk === "expansion" && (
                    <span className="text-xs px-2 py-0.5 bg-brand-teal/10 text-brand-teal rounded-full border border-brand-teal/20">
                      ↑ Expand
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
