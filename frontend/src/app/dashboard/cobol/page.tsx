"use client";

import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Terminal, Upload, FileCode2, AlertTriangle, CheckCircle2,
  ChevronDown, Download, Zap, RefreshCw, BarChart3
} from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const SAMPLE_COBOL = `       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALCPAY.
       AUTHOR. JARVIISAI-DEMO.
      *
      * CALCULATE EMPLOYEE PAYROLL
      *
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-EMPLOYEE-RECORD.
          05 WS-EMPLOYEE-ID    PIC 9(6).
          05 WS-HOURS-WORKED   PIC 9(3)V99.
          05 WS-HOURLY-RATE    PIC 9(4)V99.
          05 WS-GROSS-PAY      PIC 9(8)V99.
          05 WS-TAX-AMOUNT     PIC 9(7)V99.
          05 WS-NET-PAY        PIC 9(8)V99.
       01 WS-TAX-RATE          PIC V99 VALUE .25.
       01 WS-OVERTIME-RATE     PIC V99 VALUE 1.5.
       PROCEDURE DIVISION.
       000-MAIN.
           PERFORM 100-CALCULATE-GROSS
           PERFORM 200-CALCULATE-TAX
           PERFORM 300-CALCULATE-NET
           PERFORM 400-DISPLAY-RESULTS
           STOP RUN.
       100-CALCULATE-GROSS.
           IF WS-HOURS-WORKED > 40
               COMPUTE WS-GROSS-PAY = (40 * WS-HOURLY-RATE) +
                   ((WS-HOURS-WORKED - 40) * WS-HOURLY-RATE *
                   WS-OVERTIME-RATE)
           ELSE
               COMPUTE WS-GROSS-PAY = WS-HOURS-WORKED * WS-HOURLY-RATE
           END-IF.
       200-CALCULATE-TAX.
           COMPUTE WS-TAX-AMOUNT = WS-GROSS-PAY * WS-TAX-RATE.
       300-CALCULATE-NET.
           COMPUTE WS-NET-PAY = WS-GROSS-PAY - WS-TAX-AMOUNT.
       400-DISPLAY-RESULTS.
           DISPLAY 'EMPLOYEE: ' WS-EMPLOYEE-ID
           DISPLAY 'GROSS PAY: ' WS-GROSS-PAY
           DISPLAY 'TAX: ' WS-TAX-AMOUNT
           DISPLAY 'NET PAY: ' WS-NET-PAY.`;

function ComplexityBadge({ cc }: { cc: number }) {
  const cfg =
    cc <= 5  ? { label: "Low",    color: "text-brand-teal",    bg: "bg-brand-teal/10" } :
    cc <= 10 ? { label: "Medium", color: "text-brand-gold",    bg: "bg-brand-gold/10" } :
               { label: "High",   color: "text-brand-crimson", bg: "bg-brand-crimson/10" };
  return (
    <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", cfg.bg, cfg.color)}>
      CC={cc} {cfg.label}
    </span>
  );
}

export default function CobolTestingPage() {
  const [source, setSource] = useState(SAMPLE_COBOL);
  const [filename, setFilename] = useState("CALCPAY.cbl");
  const [generateTests, setGenerateTests] = useState(true);
  const [result, setResult] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<"overview"|"paragraphs"|"artifacts">("overview");
  const fileRef = useRef<HTMLInputElement>(null);

  const analyze = useMutation({
    mutationFn: () => apiClient.post("/cobol/analyze", {
      source,
      filename,
      generate_tests: generateTests,
    }),
    onSuccess: (res) => {
      setResult(res.data);
      toast.success(`Analyzed ${res.data.program_id}: ${res.data.paragraph_count} paragraphs`);
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Analysis failed"),
  });

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFilename(file.name);
    const reader = new FileReader();
    reader.onload = () => setSource(reader.result as string);
    reader.readAsText(file);
  };

  const downloadArtifact = (content: string, ext: string) => {
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${result?.program_id || "program"}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const TABS = [
    { id: "overview", label: "Overview" },
    { id: "paragraphs", label: `Paragraphs (${result?.paragraph_count || 0})` },
    { id: "artifacts", label: "Test Artifacts" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <Terminal className="w-7 h-7 text-brand-gold" />
          COBOL / Mainframe Testing
        </h1>
        <p className="text-content-muted text-sm mt-1">
          AI-powered COBOL analysis — generate test drivers, JCL stubs, and plain-English documentation
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Input panel */}
        <div className="glass-card p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-content-primary">COBOL Source</h2>
            <div className="flex gap-2">
              <input ref={fileRef} type="file" accept=".cbl,.cob,.cpy,.jcl" onChange={handleFileUpload} className="hidden" />
              <button
                onClick={() => fileRef.current?.click()}
                className="flex items-center gap-1.5 text-xs text-content-muted hover:text-brand-accent transition-colors border border-surface-border px-2.5 py-1.5 rounded-lg hover:border-brand-accent/40"
              >
                <Upload className="w-3 h-3" />
                Upload .cbl
              </button>
            </div>
          </div>

          <input
            value={filename}
            onChange={e => setFilename(e.target.value)}
            placeholder="PROGRAM.cbl"
            className="input-field text-xs font-mono"
          />

          <textarea
            value={source}
            onChange={e => setSource(e.target.value)}
            rows={20}
            className="input-field resize-none text-xs font-mono leading-relaxed"
            placeholder="Paste your COBOL source here..."
          />

          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={generateTests} onChange={e => setGenerateTests(e.target.checked)} className="w-4 h-4 accent-brand-accent" />
              <span className="text-sm text-content-secondary">Generate test artifacts with AI</span>
            </label>
            <motion.button
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
              onClick={() => analyze.mutate()}
              disabled={analyze.isPending || !source.trim()}
              className="btn-primary flex items-center gap-2"
            >
              {analyze.isPending ? (
                <><RefreshCw className="w-4 h-4 animate-spin" />Analyzing...</>
              ) : (
                <><Zap className="w-4 h-4" />Analyze</>
              )}
            </motion.button>
          </div>
        </div>

        {/* Results panel */}
        <div className="space-y-4">
          {!result && !analyze.isPending && (
            <div className="glass-card p-12 text-center">
              <FileCode2 className="w-10 h-10 text-surface-muted mx-auto mb-3" />
              <p className="text-content-muted text-sm">Paste COBOL source and click Analyze</p>
              <p className="text-xs text-content-muted mt-1">A sample COBOL program is preloaded</p>
            </div>
          )}

          {analyze.isPending && (
            <div className="glass-card p-8 text-center">
              <Terminal className="w-8 h-8 text-brand-gold mx-auto mb-3 animate-pulse" />
              <p className="text-content-primary font-semibold mb-1">Analyzing COBOL source...</p>
              <p className="text-content-muted text-sm">{generateTests ? "AI generating test artifacts..." : "Parsing structure..."}</p>
            </div>
          )}

          {result && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
              {/* Program header */}
              <div className="glass-card p-5">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="font-bold text-content-primary text-lg font-mono">{result.program_id}</h3>
                    <p className="text-xs text-content-muted">{filename}</p>
                  </div>
                  <ComplexityBadge cc={result.cyclomatic_complexity} />
                </div>
                <div className="grid grid-cols-4 gap-3">
                  {[
                    { label: "Lines", value: result.total_lines },
                    { label: "Paragraphs", value: result.paragraph_count },
                    { label: "Data items", value: result.data_item_count },
                    { label: "Dead para.", value: result.dead_paragraphs?.length || 0 },
                  ].map(({ label, value }) => (
                    <div key={label} className="text-center p-2.5 bg-surface-overlay rounded-lg border border-surface-border">
                      <div className="text-xl font-black text-content-primary">{value}</div>
                      <div className="text-xs text-content-muted">{label}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Warnings */}
              {result.warnings?.length > 0 && (
                <div className="glass-card p-4 border-brand-gold/20">
                  <h4 className="text-sm font-semibold text-brand-gold mb-2 flex items-center gap-1.5">
                    <AlertTriangle className="w-4 h-4" />
                    {result.warnings.length} Warning{result.warnings.length !== 1 ? "s" : ""}
                  </h4>
                  <ul className="space-y-1">
                    {result.warnings.map((w: string, i: number) => (
                      <li key={i} className="text-xs text-content-secondary font-mono">{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Tabs */}
              <div className="flex gap-1 p-1 bg-surface-overlay border border-surface-border rounded-lg w-fit">
                {TABS.map(tab => (
                  <button key={tab.id} onClick={() => setActiveTab(tab.id as any)}
                    className={cn("px-3 py-1.5 rounded text-xs font-medium transition-all",
                      activeTab === tab.id ? "bg-brand-accent/15 text-brand-accent border border-brand-accent/25" : "text-content-muted")}>
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              <AnimatePresence mode="wait">
                {activeTab === "overview" && result.test_artifacts && (
                  <motion.div key="overview" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <div className="glass-card p-5">
                      {result.test_artifacts?.test_plan?.summary && (
                        <div className="mb-4">
                          <p className="text-xs font-semibold text-content-muted mb-1">Program Summary</p>
                          <p className="text-sm text-content-secondary">{result.test_artifacts.test_plan.summary}</p>
                        </div>
                      )}
                      {result.test_artifacts?.risk_areas?.length > 0 && (
                        <div>
                          <p className="text-xs font-semibold text-content-muted mb-2">Risk Areas</p>
                          <ul className="space-y-1">
                            {result.test_artifacts.risk_areas.map((r: string, i: number) => (
                              <li key={i} className="flex items-start gap-1.5 text-xs text-content-secondary">
                                <AlertTriangle className="w-3 h-3 text-brand-gold mt-0.5 flex-shrink-0" />
                                {r}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}

                {activeTab === "paragraphs" && (
                  <motion.div key="para" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <div className="glass-card overflow-hidden max-h-80 overflow-y-auto">
                      {result.paragraphs.map((para: any) => (
                        <div key={para.name} className="flex items-center gap-3 px-4 py-2.5 border-b border-surface-border last:border-0">
                          <code className="text-xs font-mono text-brand-neon flex-1">{para.name}</code>
                          <ComplexityBadge cc={para.cyclomatic_complexity} />
                          <span className="text-xs text-content-muted">{para.lines} lines</span>
                          {para.calls?.length > 0 && (
                            <span className="text-xs text-brand-cyan">{para.calls.length} CALLs</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}

                {activeTab === "artifacts" && result.test_artifacts && (
                  <motion.div key="artifacts" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <div className="glass-card p-4 space-y-3">
                      {[
                        { label: "JCL Test Job", key: "jcl_test_stub", ext: "jcl" },
                        { label: "COBOL Test Driver", key: "cobol_driver", ext: "cbl" },
                        { label: "GnuCOBOL Tests", key: "gnucobol_tests", ext: "cbl" },
                      ].map(({ label, key, ext }) => {
                        const content = result.test_artifacts?.[key];
                        if (!content) return null;
                        return (
                          <div key={key} className="flex items-center justify-between p-3 bg-surface-overlay rounded-lg border border-surface-border">
                            <div className="flex items-center gap-2">
                              <FileCode2 className="w-4 h-4 text-brand-gold" />
                              <span className="text-sm text-content-primary">{label}</span>
                            </div>
                            <button
                              onClick={() => downloadArtifact(content, ext)}
                              className="flex items-center gap-1.5 text-xs text-brand-accent hover:text-brand-cyan transition-colors"
                            >
                              <Download className="w-3 h-3" />
                              Download .{ext}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}
