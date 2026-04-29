"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Play, Rocket, GitBranch, CheckCircle2, XCircle, Clock, ArrowRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId } from "@/store/auth";
import { cn, formatRelativeTime } from "@/lib/utils";
import Link from "next/link";
import { FilterBar, FilterState } from "@/components/filters/FilterBar";
import { useDebounce } from "@/lib/utils";

const TYPE_ICONS = { project: GitBranch, test_run: Play, deployment: Rocket };
const STATUS_COLORS: Record<string, string> = {
  passed:   "text-brand-teal",
  failed:   "text-brand-crimson",
  running:  "text-brand-accent",
  pending:  "text-content-muted",
  running2: "text-brand-cyan",
};

export default function SearchPage() {
  const orgId = useOrgId();
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<FilterState>({});
  const debouncedQuery = useDebounce(query, 300);

  const { data, isLoading } = useQuery({
    queryKey: ["search", orgId, debouncedQuery, filters],
    queryFn: () => apiClient.get(`/search?q=${encodeURIComponent(debouncedQuery)}&org_id=${orgId}${filters.status ? `&status=${filters.status}` : ""}${filters.dateFrom ? `&date_from=${filters.dateFrom}` : ""}${filters.dateTo ? `&date_to=${filters.dateTo}` : ""}&limit=30`).then(r => r.data),
    enabled: !!orgId && debouncedQuery.length >= 2,
  });

  const results = data?.results || [];
  const total = data?.total || 0;

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <Search className="w-7 h-7 text-brand-accent" />
          Search
        </h1>
        <p className="text-content-muted text-sm mt-1">
          Search across all projects, test runs, deployments, and findings
        </p>
      </div>

      {/* Search input */}
      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-content-muted" />
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search projects, runs, branches, commits..."
          autoFocus
          className="input-field pl-12 text-base h-12"
        />
        {isLoading && (
          <div className="absolute right-4 top-1/2 -translate-y-1/2">
            <div className="w-4 h-4 border-2 border-brand-accent border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </div>

      {/* Filters */}
      {debouncedQuery.length >= 2 && (
        <FilterBar
          filters={filters}
          onChange={setFilters}
          availableFilters={["status", "date"]}
        />
      )}

      {/* Results */}
      <AnimatePresence mode="wait">
        {debouncedQuery.length < 2 ? (
          <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="glass-card p-12 text-center">
            <Search className="w-10 h-10 text-surface-muted mx-auto mb-3" />
            <p className="text-content-muted">Type at least 2 characters to search</p>
            <p className="text-xs text-content-muted mt-1">
              Searches across: projects, test runs, branches, commit SHAs, environments
            </p>
          </motion.div>
        ) : results.length === 0 && !isLoading ? (
          <motion.div key="no-results" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="glass-card p-12 text-center">
            <Search className="w-10 h-10 text-surface-muted mx-auto mb-3" />
            <p className="text-content-primary font-semibold mb-1">No results for "{debouncedQuery}"</p>
            <p className="text-content-muted text-sm">Try a different search term or adjust your filters</p>
          </motion.div>
        ) : (
          <motion.div key="results" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="glass-card overflow-hidden">
            <div className="px-5 py-3 border-b border-surface-border">
              <span className="text-sm text-content-muted">
                {total} result{total !== 1 ? "s" : ""} for "<span className="text-content-primary">{debouncedQuery}</span>"
              </span>
            </div>
            <div className="divide-y divide-surface-border">
              {results.map((result: any, i: number) => {
                const Icon = TYPE_ICONS[result.type as keyof typeof TYPE_ICONS] || Search;
                const statusColor = STATUS_COLORS[result.status || ""] || "text-content-muted";
                return (
                  <Link key={result.id} href={result.url || "/dashboard"}>
                    <motion.div whileHover={{ x: 3 }}
                      className="flex items-center gap-4 px-5 py-3.5 hover:bg-surface-overlay transition-all cursor-pointer">
                      <div className="w-8 h-8 rounded-lg bg-surface-overlay border border-surface-border flex items-center justify-center flex-shrink-0">
                        <Icon className="w-4 h-4 text-content-muted" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-content-primary truncate">{result.title}</p>
                        <p className="text-xs text-content-muted truncate mt-0.5">{result.subtitle}</p>
                      </div>
                      <div className="flex items-center gap-3 flex-shrink-0">
                        {result.status && (
                          <span className={cn("text-xs capitalize font-medium", statusColor)}>
                            {result.status === "passed" ? <CheckCircle2 className="w-3.5 h-3.5 inline mr-1" /> :
                             result.status === "failed" ? <XCircle className="w-3.5 h-3.5 inline mr-1" /> :
                             <Clock className="w-3.5 h-3.5 inline mr-1" />}
                            {result.status}
                          </span>
                        )}
                        <span className="text-xs text-content-muted">{formatRelativeTime(result.created_at)}</span>
                        <ArrowRight className="w-3.5 h-3.5 text-content-muted" />
                      </div>
                    </motion.div>
                  </Link>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
