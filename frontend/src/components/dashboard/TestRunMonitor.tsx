"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2, XCircle, Clock, AlertCircle,
  Terminal, Play, Zap, BarChart3, RefreshCw
} from "lucide-react";
import { cn } from "@/lib/utils";

interface TestEvent {
  event: "status" | "test_result" | "log" | "complete";
  data: any;
  timestamp: number;
}

interface TestRunMonitorProps {
  runId: string;
  initialStatus?: string;
  totalTests?: number;
  onComplete?: (result: any) => void;
}

const STATUS_CONFIG = {
  pending:    { label: "Pending",    color: "text-content-muted",   bg: "bg-surface-border",    icon: Clock },
  queued:     { label: "Queued",     color: "text-content-muted",   bg: "bg-surface-border",    icon: Clock },
  crawling:   { label: "Crawling",   color: "text-brand-cyan",      bg: "bg-brand-cyan/10",     icon: Zap },
  generating: { label: "Generating", color: "text-brand-accent",    bg: "bg-brand-accent/10",   icon: Zap },
  running:    { label: "Running",    color: "text-brand-gold",      bg: "bg-brand-gold/10",     icon: Play },
  passed:     { label: "Passed",     color: "text-brand-teal",      bg: "bg-brand-teal/10",     icon: CheckCircle2 },
  failed:     { label: "Failed",     color: "text-brand-crimson",   bg: "bg-brand-crimson/10",  icon: XCircle },
  error:      { label: "Error",      color: "text-brand-crimson",   bg: "bg-brand-crimson/10",  icon: AlertCircle },
  cancelled:  { label: "Cancelled",  color: "text-content-muted",   bg: "bg-surface-border",    icon: AlertCircle },
};

export default function TestRunMonitor({
  runId, initialStatus = "pending", totalTests = 0, onComplete
}: TestRunMonitorProps) {
  const [status, setStatus] = useState(initialStatus);
  const [logs, setLogs] = useState<string[]>([]);
  const [passed, setPassed] = useState(0);
  const [failed, setFailed] = useState(0);
  const [progress, setProgress] = useState(0);
  const [connected, setConnected] = useState(false);
  const [stage, setStage] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  const statusCfg = STATUS_CONFIG[status as keyof typeof STATUS_CONFIG] || STATUS_CONFIG.pending;
  const StatusIcon = statusCfg.icon;
  const isActive = ["queued", "crawling", "generating", "running"].includes(status);
  const isComplete = ["passed", "failed", "error", "cancelled"].includes(status);

  useEffect(() => {
    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8005";
    const wsUrl = `${wsBase}/ws/runs/${runId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      addLog("🔌 Connected to live event stream");
    };

    ws.onmessage = (e) => {
      try {
        const event: TestEvent = { ...JSON.parse(e.data), timestamp: Date.now() };
        handleEvent(event);
      } catch {}
    };

    ws.onclose = () => {
      setConnected(false);
    };

    ws.onerror = () => {
      addLog("⚠️ WebSocket connection error — check test executor service");
    };

    return () => ws.close();
  }, [runId]);

  // Auto-scroll logs
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const handleEvent = (event: TestEvent) => {
    const { data } = event;

    if (event.event === "status") {
      setStatus(data.status);
      if (data.stage) setStage(data.stage);
      const stageMessages: Record<string, string> = {
        crawling: "🕷️  Crawling application...",
        generating: "🤖 AI generating test suite...",
        executing: "⚡ Executing tests...",
      };
      if (data.stage && stageMessages[data.stage]) {
        addLog(stageMessages[data.stage]);
      }
    }

    if (event.event === "test_result") {
      const isPass = data.status === "passed";
      if (isPass) {
        setPassed(p => p + 1);
        addLog(`  ✓ ${data.name} (${data.duration_ms}ms)`);
      } else {
        setFailed(f => f + 1);
        addLog(`  ✗ ${data.name}: ${data.error_message || "failed"}`);
      }
      if (totalTests > 0) {
        setProgress(Math.round((passed + failed + 1) / totalTests * 100));
      }
    }

    if (event.event === "log") {
      if (data.line) addLog(data.line);
    }

    if (event.event === "complete") {
      setStatus(data.status);
      setPassed(data.passed || 0);
      setFailed(data.failed || 0);
      addLog(`\n✅ Run complete: ${data.passed}/${data.total} passed in ${data.duration_seconds}s`);
      wsRef.current?.close();
      onComplete?.(data);
    }
  };

  const addLog = (line: string) => {
    setLogs(l => [...l.slice(-200), line]);  // keep last 200 lines
  };

  const total = passed + failed;
  const passRate = total > 0 ? Math.round(passed / total * 100) : null;

  return (
    <div className="space-y-4">
      {/* Status header */}
      <div className="glass-card p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center", statusCfg.bg)}>
              {isActive ? (
                <StatusIcon className={cn("w-5 h-5 animate-pulse", statusCfg.color)} />
              ) : (
                <StatusIcon className={cn("w-5 h-5", statusCfg.color)} />
              )}
            </div>
            <div>
              <div className="font-semibold text-content-primary flex items-center gap-2">
                {statusCfg.label}
                {isActive && (
                  <span className="flex gap-1">
                    {[0, 1, 2].map(i => (
                      <motion.span
                        key={i}
                        className="w-1.5 h-1.5 bg-brand-accent rounded-full"
                        animate={{ scale: [1, 1.4, 1], opacity: [0.5, 1, 0.5] }}
                        transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
                      />
                    ))}
                  </span>
                )}
              </div>
              {stage && <p className="text-xs text-content-muted capitalize">{stage.replace("_", " ")}</p>}
            </div>
          </div>
          <div className={cn("flex items-center gap-1.5 text-xs", connected ? "text-brand-teal" : "text-content-muted")}>
            <div className={cn("w-2 h-2 rounded-full", connected ? "bg-brand-teal animate-pulse" : "bg-surface-border")} />
            {connected ? "Live" : "Disconnected"}
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "Passed", value: passed, color: "text-brand-teal" },
            { label: "Failed", value: failed, color: "text-brand-crimson" },
            { label: "Total", value: total, color: "text-content-primary" },
            { label: "Pass Rate", value: passRate !== null ? `${passRate}%` : "—", color: passRate !== null && passRate >= 80 ? "text-brand-teal" : "text-content-secondary" },
          ].map(({ label, value, color }) => (
            <div key={label} className="text-center p-2 bg-surface-overlay rounded-lg border border-surface-border">
              <div className={cn("text-xl font-black", color)}>{value}</div>
              <div className="text-xs text-content-muted">{label}</div>
            </div>
          ))}
        </div>

        {/* Progress bar */}
        {(isActive || isComplete) && totalTests > 0 && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-xs text-content-muted mb-1">
              <span>Progress</span>
              <span>{progress}%</span>
            </div>
            <div className="h-1.5 bg-surface-border rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-brand-accent rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${isComplete ? 100 : progress}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Live log stream */}
      <div className="glass-card">
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-surface-border">
          <Terminal className="w-4 h-4 text-content-muted" />
          <span className="text-sm font-medium text-content-secondary">Live Output</span>
        </div>
        <div className="h-64 overflow-y-auto p-4 font-mono text-xs text-brand-neon/80 space-y-0.5">
          {logs.length === 0 && (
            <p className="text-content-muted italic">Waiting for events...</p>
          )}
          {logs.map((line, i) => (
            <div key={i} className={cn(
              line.startsWith("  ✓") ? "text-brand-teal" :
              line.startsWith("  ✗") ? "text-brand-crimson" :
              line.includes("Error") || line.includes("FAIL") ? "text-brand-crimson" :
              "text-brand-neon/70"
            )}>
              {line}
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  );
}
