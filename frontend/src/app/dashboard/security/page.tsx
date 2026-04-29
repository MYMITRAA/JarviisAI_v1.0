"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Shield, AlertCircle, AlertTriangle, Info, CheckCircle2,
  ChevronDown, Zap, RefreshCw, ExternalLink, Lock
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId, useOrgSlug } from "@/store/auth";
import { cn, formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

const SEVERITY_CONFIG = {
  critical: { color: "text-red-400",     bg: "bg-red-400/10",     border: "border-red-400/30",     icon: AlertCircle,   label: "Critical" },
  high:     { color: "text-brand-crimson",bg: "bg-brand-crimson/10",border: "border-brand-crimson/30",icon: AlertTriangle, label: "High" },
  medium:   { color: "text-brand-gold",  bg: "bg-brand-gold/10",  border: "border-brand-gold/30",  icon: AlertTriangle, label: "Medium" },
  low:      { color: "text-brand-cyan",  bg: "bg-brand-cyan/10",  border: "border-brand-cyan/30",  icon: Info,          label: "Low" },
  info:     { color: "text-content-muted",bg: "bg-surface-border", border: "border-surface-border", icon: Info,          label: "Info" },
};

function SecurityScore({ score, grade }: { score: number; grade: string }) {
  const color = score >= 90 ? "text-brand-teal" : score >= 70 ? "text-brand-gold" : "text-brand-crimson";
  const gradeColor = grade.startsWith("A") ? "text-brand-teal" : grade === "B" ? "text-brand-gold" : "text-brand-crimson";
  const circumference = 2 * Math.PI * 54;
  const progress = (score / 100) * circumference;

  return (
    <div className="flex items-center gap-6">
      <div className="relative w-32 h-32">
        <svg className="w-32 h-32 -rotate-90" viewBox="0 0 128 128">
          <circle cx="64" cy="64" r="54" fill="none" stroke="var(--surface-border)" strokeWidth="8" />
          <circle
            cx="64" cy="64" r="54" fill="none"
            stroke={score >= 90 ? "#14b8a6" : score >= 70 ? "#f59e0b" : "#ef4444"}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={`${progress} ${circumference}`}
            className="transition-all duration-1000"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn("text-3xl font-black", color)}>{score}</span>
          <span className="text-xs text-content-muted">/ 100</span>
        </div>
      </div>
      <div>
        <div className={cn("text-6xl font-black", gradeColor)}>{grade}</div>
        <p className="text-content-muted text-sm mt-1">Security Grade</p>
      </div>
    </div>
  );
}

function FindingCard({ finding }: { finding: any }) {
  const [open, setOpen] = useState(false);
  const cfg = SEVERITY_CONFIG[finding.severity as keyof typeof SEVERITY_CONFIG] || SEVERITY_CONFIG.info;
  const Icon = cfg.icon;

  return (
    <div className={cn("border rounded-lg overflow-hidden transition-all", cfg.border)}>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 p-4 hover:bg-surface-overlay transition-colors text-left"
      >
        <span className={cn("flex items-center gap-1.5 text-xs font-bold px-2 py-0.5 rounded-full min-w-[72px]", cfg.bg, cfg.color)}>
          <Icon className="w-3 h-3" />
          {cfg.label}
        </span>
        <div className="flex-1">
          <p className="text-sm font-medium text-content-primary">{finding.title}</p>
          <p className="text-xs text-content-muted">{finding.category}</p>
        </div>
        {finding.owasp && (
          <span className="text-xs text-content-muted bg-surface-border px-2 py-0.5 rounded font-mono">
            {finding.owasp}
          </span>
        )}
        {finding.cwe && (
          <span className="text-xs text-content-muted bg-surface-border px-2 py-0.5 rounded font-mono">
            {finding.cwe}
          </span>
        )}
        <ChevronDown className={cn("w-4 h-4 text-content-muted transition-transform flex-shrink-0", open && "rotate-180")} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className={cn("border-t overflow-hidden", cfg.border)}
          >
            <div className="p-4 space-y-3">
              <div>
                <p className="text-xs font-semibold text-content-muted mb-1">Description</p>
                <p className="text-sm text-content-secondary">{finding.description}</p>
              </div>
              {finding.evidence && (
                <div className="bg-surface-overlay rounded p-2">
                  <p className="text-xs font-semibold text-content-muted mb-1">Evidence</p>
                  <code className="text-xs text-brand-neon font-mono">{finding.evidence}</code>
                </div>
              )}
              {finding.remediation && (
                <div className={cn("rounded-lg p-3", cfg.bg)}>
                  <p className="text-xs font-semibold mb-1" style={{ color: "inherit" }}>Fix</p>
                  <p className="text-xs text-content-secondary">{finding.remediation}</p>
                </div>
              )}
              {finding.url && finding.url !== finding.description && (
                <a href={finding.url} target="_blank" rel="noopener noreferrer"
                   className="flex items-center gap-1 text-xs text-brand-accent hover:underline">
                  <ExternalLink className="w-3 h-3" />
                  {finding.url}
                </a>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function SecurityPage() {
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const qc = useQueryClient();
  const [scanUrl, setScanUrl] = useState("");
  const [scanDepth, setScanDepth] = useState("standard");
  const [activeScanId, setActiveScanId] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<any>(null);
  const [severityFilter, setSeverityFilter] = useState("all");

  const runScan = useMutation({
    mutationFn: (data: { url: string; depth: string }) =>
      apiClient.post("/security/scan/sync", {
        scan_id: `scan-${Date.now()}`,
        project_id: "manual",
        org_id: orgId,
        url: data.url,
        depth: data.depth,
      }),
    onSuccess: (res) => {
      setScanResult(res.data);
      toast.success(`Scan complete — Grade: ${res.data.grade}`);
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Scan failed"),
  });

  const handleScan = () => {
    if (!scanUrl) { toast.error("Enter a URL to scan"); return; }
    setScanResult(null);
    runScan.mutate({ url: scanUrl, depth: scanDepth });
  };

  const findings = scanResult?.findings || [];
  const filtered = severityFilter === "all" ? findings : findings.filter((f: any) => f.severity === severityFilter);
  const summary = scanResult?.summary || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
            <Shield className="w-7 h-7 text-brand-cyan" />
            Security Scanner
          </h1>
          <p className="text-content-muted text-sm mt-1">OWASP Top 10 · Security Headers · Injection · CORS · Rate Limiting</p>
        </div>
      </div>

      {/* Scan input */}
      <div className="glass-card p-6">
        <h2 className="font-semibold text-content-primary mb-4">Run Security Scan</h2>
        <div className="flex gap-3">
          <input
            value={scanUrl}
            onChange={e => setScanUrl(e.target.value)}
            placeholder="https://myapp.com"
            className="input-field flex-1 font-mono text-sm"
            onKeyDown={e => e.key === "Enter" && handleScan()}
          />
          <select
            value={scanDepth}
            onChange={e => setScanDepth(e.target.value)}
            className="input-field w-36 text-sm"
          >
            <option value="quick">Quick</option>
            <option value="standard">Standard</option>
            <option value="deep">Deep</option>
          </select>
          <motion.button
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            onClick={handleScan}
            disabled={runScan.isPending}
            className="btn-primary flex items-center gap-2 whitespace-nowrap"
          >
            {runScan.isPending ? (
              <><RefreshCw className="w-4 h-4 animate-spin" /> Scanning...</>
            ) : (
              <><Shield className="w-4 h-4" /> Start Scan</>
            )}
          </motion.button>
        </div>
        <p className="text-xs text-content-muted mt-2">
          All scans are non-destructive. No data is modified. Deep scan includes browser-based checks.
        </p>
      </div>

      {/* Results */}
      {runScan.isPending && (
        <div className="glass-card p-8 text-center">
          <Shield className="w-10 h-10 text-brand-cyan mx-auto mb-3 animate-pulse" />
          <p className="font-semibold text-content-primary mb-1">Scanning {scanUrl}...</p>
          <p className="text-content-muted text-sm">Checking headers, CORS, injection indicators, exposed paths...</p>
        </div>
      )}

      {scanResult && !runScan.isPending && (
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">
          {/* Score card */}
          <div className="glass-card p-6">
            <div className="flex items-center justify-between flex-wrap gap-6">
              <SecurityScore score={scanResult.score} grade={scanResult.grade} />

              <div className="grid grid-cols-5 gap-3">
                {["critical","high","medium","low","info"].map(sev => {
                  const cfg = SEVERITY_CONFIG[sev as keyof typeof SEVERITY_CONFIG];
                  return (
                    <div key={sev} className={cn("text-center p-3 rounded-lg border", cfg.bg, cfg.border)}>
                      <div className={cn("text-2xl font-black", cfg.color)}>{summary[sev] || 0}</div>
                      <div className="text-xs text-content-muted capitalize">{sev}</div>
                    </div>
                  );
                })}
              </div>

              <div className="text-right">
                <p className="text-xs text-content-muted mb-1">Scan completed in</p>
                <p className="font-semibold text-content-primary">{scanResult.duration_seconds}s</p>
                <p className="text-xs text-content-muted mt-2">{scanResult.total_checks} checks performed</p>
              </div>
            </div>
          </div>

          {/* Findings */}
          <div className="glass-card overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-surface-border">
              <h2 className="font-semibold text-content-primary">{findings.length} Findings</h2>
              <div className="flex gap-1">
                {["all", ...Object.keys(SEVERITY_CONFIG)].map(sev => (
                  <button
                    key={sev}
                    onClick={() => setSeverityFilter(sev)}
                    className={cn(
                      "px-2.5 py-1 rounded text-xs font-medium capitalize transition-all",
                      severityFilter === sev
                        ? "bg-brand-accent/15 text-brand-accent border border-brand-accent/30"
                        : "text-content-muted hover:text-content-secondary"
                    )}
                  >
                    {sev}
                  </button>
                ))}
              </div>
            </div>
            <div className="p-4 space-y-2">
              {filtered.length === 0 ? (
                <div className="py-8 text-center">
                  <CheckCircle2 className="w-8 h-8 text-brand-teal mx-auto mb-2" />
                  <p className="text-content-muted text-sm">No {severityFilter === "all" ? "" : severityFilter} findings</p>
                </div>
              ) : (
                filtered.map((f: any, i: number) => <FindingCard key={i} finding={f} />)
              )}
            </div>
          </div>
        </motion.div>
      )}

      {!scanResult && !runScan.isPending && (
        <div className="glass-card p-12 text-center">
          <Lock className="w-10 h-10 text-surface-muted mx-auto mb-3" />
          <p className="text-content-primary font-semibold mb-1">Run your first security scan</p>
          <p className="text-content-muted text-sm max-w-md mx-auto">
            JarviisAI checks for OWASP Top 10 vulnerabilities, security header misconfigurations, CORS issues,
            injection indicators, and exposed sensitive paths.
          </p>
        </div>
      )}
    </div>
  );
}
