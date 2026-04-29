"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Users, Search, Shield, Mail, Clock, ChevronDown } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { cn, formatRelativeTime } from "@/lib/utils";

export default function AdminUsersPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-orgs", page, search],
    queryFn: () => apiClient.get(`/organizations?page=${page}&page_size=20${search ? `&search=${encodeURIComponent(search)}` : ""}`).then(r => r.data),
    staleTime: 30_000,
  });

  // Auth service returns array directly for superadmin list
  const orgs = Array.isArray(data) ? data : (data?.items || []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <Users className="w-7 h-7 text-brand-accent" />
          Organizations
        </h1>
        <p className="text-content-muted text-sm mt-1">All organizations across the platform</p>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-content-muted" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by email or name..."
            className="input-field pl-9"
          />
        </div>
      </div>

      <div className="glass-card overflow-hidden">
        <div className="grid grid-cols-12 gap-4 px-5 py-3 border-b border-surface-border text-xs font-semibold text-content-muted uppercase tracking-wider">
          <div className="col-span-4">Organization</div>
          <div className="col-span-3">Org ID</div>
          <div className="col-span-2">Plan</div>
          <div className="col-span-2">Members</div>
          <div className="col-span-1">Joined</div>
        </div>

        {isLoading ? (
          <div className="p-6 space-y-3">
            {[1,2,3,4,5].map(i => (
              <div key={i} className="h-12 bg-surface-border rounded animate-pulse" />
            ))}
          </div>
        ) : orgs.length === 0 ? (
          <div className="py-12 text-center">
            <Users className="w-10 h-10 text-surface-muted mx-auto mb-3" />
            <p className="text-content-muted">No users found</p>
            <p className="text-xs text-content-muted mt-1">User management requires admin API access</p>
          </div>
        ) : (
          orgs.map((org: any) => (
            <div key={org.id} className="grid grid-cols-12 gap-4 px-5 py-3.5 border-b border-surface-border last:border-0 hover:bg-surface-overlay transition-colors">
              <div className="col-span-4 flex items-center gap-3 min-w-0">
                <div className="w-8 h-8 rounded-xl bg-brand-accent/20 border border-brand-accent/30 flex items-center justify-center flex-shrink-0">
                  <span className="text-xs font-bold text-brand-accent">
                    {org.name?.[0] || "?"}
                  </span>
                </div>
                <div className="min-w-0">
                  <p className="text-sm text-content-primary truncate font-medium">{org.name}</p>
                  <p className="text-xs text-content-muted font-mono truncate">{org.slug}</p>
                </div>
              </div>
              <div className="col-span-3 flex items-center">
                <span className="text-xs text-content-muted font-mono truncate">{org.id?.slice(0,12)}…</span>
              </div>
              <div className="col-span-2 flex items-center">
                <span className={cn("text-xs px-2 py-0.5 rounded-full capitalize",
                  org.plan === "enterprise" ? "bg-brand-gold/10 text-brand-gold" :
                  org.plan === "team" ? "bg-brand-teal/10 text-brand-teal" :
                  org.plan === "pro" ? "bg-brand-accent/10 text-brand-accent" :
                  "bg-surface-border text-content-muted"
                )}>
                  {org.plan || "starter"}
                </span>
              </div>
              <div className="col-span-2 flex items-center">
                <span className="text-xs text-content-muted">—</span>
              </div>
              <div className="col-span-1 flex items-center">
                <span className="text-xs text-content-muted">{org.created_at ? formatRelativeTime(org.created_at) : "—"}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
