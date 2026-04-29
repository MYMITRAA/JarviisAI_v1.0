"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { FileText, Download, RefreshCw, Calendar, FileBarChart, Shield, Zap, Rocket, CreditCard, Lock } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId } from "@/store/auth";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const REPORT_TYPES = [
  { id: "test_reliability",    name: "Test Reliability",      icon: FileBarChart, color: "text-brand-teal",    desc: "Pass rates, flaky tests, most-failed files" },
  { id: "deploy_stability",    name: "Deploy Stability",      icon: Rocket,       color: "text-brand-cyan",    desc: "Rollback rates, MTTR, deploy frequency" },
  { id: "healing_effectiveness",name:"Healing Effectiveness", icon: Zap,          color: "text-brand-gold",    desc: "Auto-heal ROI, estimated hours saved" },
  { id: "security_risk",       name: "Security Risk",         icon: Shield,       color: "text-brand-crimson", desc: "All findings, scores, remediation status" },
  { id: "usage_cost",          name: "Usage & Cost",          icon: CreditCard,   color: "text-brand-accent",  desc: "Plan usage, overage, cost per test estimate" },
  { id: "executive_summary",   name: "Executive Summary",     icon: FileText,     color: "text-brand-accent",  desc: "Full platform summary for leadership" },
  { id: "compliance_evidence", name: "Compliance Evidence",   icon: Lock,         color: "text-brand-gold",    desc: "SOC2/GDPR evidence pack, audit trail" },
  { id: "audit_access",        name: "Audit Access Log",      icon: FileText,     color: "text-content-muted", desc: "All user actions, config changes, access events" },
];

const FORMAT_OPTIONS = [
  { value: "csv",  label: "CSV",  desc: "Spreadsheet-compatible" },
  { value: "json", label: "JSON", desc: "Machine-readable" },
  { value: "pdf",  label: "HTML", desc: "Print-ready report" },
];

const PERIOD_OPTIONS = [
  { value: 7,  label: "Last 7 days" },
  { value: 30, label: "Last 30 days" },
  { value: 90, label: "Last 90 days" },
];

export default function ReportsPage() {
  const orgId = useOrgId();
  const [selectedType, setSelectedType] = useState("executive_summary");
  const [format, setFormat] = useState("csv");
  const [days, setDays] = useState(30);
  const [generating, setGenerating] = useState<string | null>(null);

  const generateReport = async (reportType: string) => {
    setGenerating(reportType);
    try {
      const response = await apiClient.post(
        "/reports/generate",
        { org_id: orgId, report_type: reportType, format, days },
        { responseType: format === "json" ? "json" : "blob" }
      );

      if (format === "json") {
        const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `jarviis_${reportType}_${new Date().toISOString().split("T")[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        const url = URL.createObjectURL(response.data as Blob);
        const a = document.createElement("a");
        a.href = url;
        const ext = format === "pdf" ? "html" : format;
        a.download = `jarviis_${reportType}_${new Date().toISOString().split("T")[0]}.${ext}`;
        a.click();
        URL.revokeObjectURL(url);
      }
      toast.success(`${REPORT_TYPES.find(r => r.id === reportType)?.name} downloaded`);
    } catch (e: any) {
      toast.error("Report generation failed");
    } finally {
      setGenerating(null);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <FileText className="w-7 h-7 text-brand-accent" />
          Reports
        </h1>
        <p className="text-content-muted text-sm mt-1">
          Generate, export, and schedule reports for your team and stakeholders
        </p>
      </div>

      {/* Global config */}
      <div className="glass-card p-5">
        <h2 className="font-semibold text-content-primary mb-4">Report Configuration</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-medium text-content-muted uppercase tracking-wider mb-2 block">Time Period</label>
            <div className="flex gap-2">
              {PERIOD_OPTIONS.map(opt => (
                <button key={opt.value} onClick={() => setDays(opt.value)}
                  className={cn("flex-1 py-2 rounded-lg text-xs font-medium border transition-all",
                    days === opt.value ? "border-brand-accent bg-brand-accent/10 text-brand-accent" : "border-surface-border text-content-muted hover:border-surface-muted")}>
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-content-muted uppercase tracking-wider mb-2 block">Export Format</label>
            <div className="flex gap-2">
              {FORMAT_OPTIONS.map(opt => (
                <button key={opt.value} onClick={() => setFormat(opt.value)}
                  className={cn("flex-1 py-2 rounded-lg text-xs font-medium border transition-all",
                    format === opt.value ? "border-brand-accent bg-brand-accent/10 text-brand-accent" : "border-surface-border text-content-muted hover:border-surface-muted")}>
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Report cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {REPORT_TYPES.map((report, i) => {
          const isGenerating = generating === report.id;
          return (
            <motion.div
              key={report.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              whileHover={{ y: -2 }}
              className="glass-card p-5 hover:border-brand-accent/30 transition-all"
            >
              <div className="flex items-start gap-3 mb-3">
                <div className={cn("p-2 rounded-lg bg-surface-overlay border border-surface-border flex-shrink-0")}>
                  <report.icon className={cn("w-5 h-5", report.color)} />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-content-primary text-sm">{report.name}</h3>
                  <p className="text-xs text-content-muted mt-0.5">{report.desc}</p>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-content-muted">
                  <Calendar className="w-3 h-3" />
                  Last {days} days · {FORMAT_OPTIONS.find(f => f.value === format)?.label}
                </div>
                <motion.button
                  whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                  onClick={() => generateReport(report.id)}
                  disabled={!!generating}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-brand-accent/10 text-brand-accent border border-brand-accent/25 hover:bg-brand-accent/20 transition-all disabled:opacity-50"
                >
                  {isGenerating ? (
                    <><RefreshCw className="w-3 h-3 animate-spin" /> Generating...</>
                  ) : (
                    <><Download className="w-3 h-3" /> Generate</>
                  )}
                </motion.button>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Scheduled reports note */}
      <div className="glass-card p-5 border-surface-muted/50">
        <div className="flex items-start gap-3">
          <Calendar className="w-5 h-5 text-brand-gold mt-0.5 flex-shrink-0" />
          <div>
            <h3 className="font-semibold text-content-primary text-sm mb-1">Scheduled Reports</h3>
            <p className="text-xs text-content-muted">
              Automatically deliver reports to your team on a schedule. Configure weekly Executive Summaries,
              monthly Compliance Evidence Packs, or daily Security Risk reports.
              Available on <span className="text-brand-gold">Team</span> and <span className="text-brand-gold">Enterprise</span> plans.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
