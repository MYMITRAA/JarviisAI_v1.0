"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Filter, X, Calendar, ChevronDown, Save, Share2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface FilterState {
  status?: string;
  dateFrom?: string;
  dateTo?: string;
  project?: string;
  environment?: string;
  severity?: string;
  triggerType?: string;
  search?: string;
}

interface FilterBarProps {
  filters: FilterState;
  onChange: (filters: FilterState) => void;
  availableFilters?: Array<"status" | "date" | "project" | "environment" | "severity" | "trigger">;
  statusOptions?: Array<{ value: string; label: string; color?: string }>;
  projects?: Array<{ id: string; name: string }>;
  onSave?: (name: string, filters: FilterState) => void;
  className?: string;
}

const DEFAULT_STATUS_OPTIONS = [
  { value: "passed",   label: "Passed",    color: "text-brand-teal" },
  { value: "failed",   label: "Failed",    color: "text-brand-crimson" },
  { value: "running",  label: "Running",   color: "text-brand-accent" },
  { value: "pending",  label: "Pending",   color: "text-content-muted" },
  { value: "error",    label: "Error",     color: "text-brand-gold" },
];

export function FilterBar({
  filters,
  onChange,
  availableFilters = ["status", "date", "project"],
  statusOptions = DEFAULT_STATUS_OPTIONS,
  projects = [],
  onSave,
  className,
}: FilterBarProps) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveName, setSaveName] = useState("");

  const activeCount = Object.values(filters).filter(Boolean).length;
  const hasFilters = activeCount > 0;

  const update = (key: keyof FilterState, value: string | undefined) => {
    onChange({ ...filters, [key]: value || undefined });
  };

  const clear = () => onChange({});

  return (
    <div className={cn("relative", className)}>
      <div className="flex items-center gap-2 flex-wrap">
        {/* Filter trigger */}
        <motion.button
          whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          onClick={() => setOpen(o => !o)}
          className={cn(
            "flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium transition-all",
            hasFilters
              ? "border-brand-accent/40 bg-brand-accent/10 text-brand-accent"
              : "border-surface-border text-content-muted hover:border-surface-muted"
          )}
        >
          <Filter className="w-3.5 h-3.5" />
          Filters
          {hasFilters && (
            <span className="bg-brand-accent text-white text-xs rounded-full w-4 h-4 flex items-center justify-center font-bold">
              {activeCount}
            </span>
          )}
          <ChevronDown className={cn("w-3.5 h-3.5 transition-transform", open && "rotate-180")} />
        </motion.button>

        {/* Active filter pills */}
        {filters.status && (
          <FilterPill label={`Status: ${filters.status}`} onRemove={() => update("status", undefined)} />
        )}
        {filters.dateFrom && (
          <FilterPill label={`From: ${filters.dateFrom}`} onRemove={() => update("dateFrom", undefined)} />
        )}
        {filters.dateTo && (
          <FilterPill label={`To: ${filters.dateTo}`} onRemove={() => update("dateTo", undefined)} />
        )}
        {filters.project && (
          <FilterPill
            label={`Project: ${projects.find(p => p.id === filters.project)?.name || filters.project}`}
            onRemove={() => update("project", undefined)}
          />
        )}
        {filters.environment && (
          <FilterPill label={`Env: ${filters.environment}`} onRemove={() => update("environment", undefined)} />
        )}
        {filters.severity && (
          <FilterPill label={`Severity: ${filters.severity}`} onRemove={() => update("severity", undefined)} />
        )}

        {hasFilters && (
          <button onClick={clear} className="text-xs text-content-muted hover:text-brand-crimson transition-colors flex items-center gap-1">
            <X className="w-3 h-3" /> Clear all
          </button>
        )}
      </div>

      {/* Filter panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            role="dialog" aria-label="Filter options" className="absolute left-0 top-full mt-2 z-50 w-96 glass-card p-5 shadow-2xl border-brand-accent/20"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-content-primary text-sm">Filter</h3>
              <button onClick={() => setOpen(false)} className="text-content-muted hover:text-content-primary">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4">
              {/* Status */}
              {availableFilters.includes("status") && (
                <div>
                  <label className="text-xs font-medium text-content-muted uppercase tracking-wider mb-2 block">Status</label>
                  <div className="flex flex-wrap gap-2">
                    {statusOptions.map(opt => (
                      <button
                        key={opt.value}
                        onClick={() => update("status", filters.status === opt.value ? undefined : opt.value)}
                        className={cn(
                          "px-2.5 py-1 rounded-lg text-xs font-medium border transition-all",
                          filters.status === opt.value
                            ? "border-brand-accent bg-brand-accent/15 text-brand-accent"
                            : "border-surface-border text-content-muted hover:border-surface-muted"
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Date range */}
              {availableFilters.includes("date") && (
                <div>
                  <label className="text-xs font-medium text-content-muted uppercase tracking-wider mb-2 block">Date Range</label>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <p className="text-xs text-content-muted mb-1">From</p>
                      <input
                        type="date"
                        value={filters.dateFrom || ""}
                        onChange={e => update("dateFrom", e.target.value)}
                        className="input-field text-xs py-1.5"
                      />
                    </div>
                    <div>
                      <p className="text-xs text-content-muted mb-1">To</p>
                      <input
                        type="date"
                        value={filters.dateTo || ""}
                        onChange={e => update("dateTo", e.target.value)}
                        className="input-field text-xs py-1.5"
                      />
                    </div>
                  </div>
                  <div className="flex gap-2 mt-2">
                    {[
                      { label: "Today", days: 0 },
                      { label: "7d", days: 7 },
                      { label: "30d", days: 30 },
                      { label: "90d", days: 90 },
                    ].map(({ label, days }) => (
                      <button
                        key={label}
                        onClick={() => {
                          const to = new Date().toISOString().split("T")[0];
                          const from = days === 0 ? to : new Date(Date.now() - days * 86400000).toISOString().split("T")[0];
                          onChange({ ...filters, dateFrom: from, dateTo: to });
                        }}
                        className="text-xs px-2 py-1 border border-surface-border rounded text-content-muted hover:border-brand-accent/40 hover:text-brand-accent transition-all"
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Project */}
              {availableFilters.includes("project") && projects.length > 0 && (
                <div>
                  <label className="text-xs font-medium text-content-muted uppercase tracking-wider mb-2 block">Project</label>
                  <select
                    value={filters.project || ""}
                    onChange={e => update("project", e.target.value)}
                    className="input-field text-sm"
                  >
                    <option value="">All Projects</option>
                    {projects.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Environment */}
              {availableFilters.includes("environment") && (
                <div>
                  <label className="text-xs font-medium text-content-muted uppercase tracking-wider mb-2 block">Environment</label>
                  <div className="flex gap-2">
                    {["development", "staging", "production"].map(env => (
                      <button
                        key={env}
                        onClick={() => update("environment", filters.environment === env ? undefined : env)}
                        className={cn(
                          "px-2.5 py-1 rounded-lg text-xs font-medium border capitalize transition-all",
                          filters.environment === env
                            ? "border-brand-accent bg-brand-accent/15 text-brand-accent"
                            : "border-surface-border text-content-muted hover:border-surface-muted"
                        )}
                      >
                        {env}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Severity */}
              {availableFilters.includes("severity") && (
                <div>
                  <label className="text-xs font-medium text-content-muted uppercase tracking-wider mb-2 block">Severity</label>
                  <div className="flex gap-2">
                    {["critical", "high", "medium", "low"].map(sev => (
                      <button
                        key={sev}
                        onClick={() => update("severity", filters.severity === sev ? undefined : sev)}
                        className={cn(
                          "px-2.5 py-1 rounded-lg text-xs font-medium border capitalize transition-all",
                          filters.severity === sev
                            ? "border-brand-accent bg-brand-accent/15 text-brand-accent"
                            : "border-surface-border text-content-muted hover:border-surface-muted"
                        )}
                      >
                        {sev}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Apply */}
            <div className="mt-4 flex justify-between items-center border-t border-surface-border pt-4">
              <button onClick={clear} className="text-xs text-content-muted hover:text-brand-crimson transition-colors">
                Clear all
              </button>
              <button onClick={() => setOpen(false)} className="btn-primary text-sm py-1.5">
                Apply Filters
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function FilterPill({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1 bg-brand-accent/10 border border-brand-accent/25 rounded-full text-xs text-brand-accent">
      {label}
      <button onClick={onRemove} className="hover:text-brand-crimson transition-colors">
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}
