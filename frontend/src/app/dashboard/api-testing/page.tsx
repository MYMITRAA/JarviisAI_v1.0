"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Code2, Upload, Play, CheckCircle2, XCircle, Clock,
  RefreshCw, ChevronDown, AlertCircle, Zap, Link
} from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId, useOrgSlug } from "@/store/auth";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const METHOD_COLORS: Record<string, string> = {
  GET:    "text-brand-teal   bg-brand-teal/10   border-brand-teal/30",
  POST:   "text-brand-accent bg-brand-accent/10 border-brand-accent/30",
  PUT:    "text-brand-gold   bg-brand-gold/10   border-brand-gold/30",
  PATCH:  "text-brand-cyan   bg-brand-cyan/10   border-brand-cyan/30",
  DELETE: "text-brand-crimson bg-brand-crimson/10 border-brand-crimson/30",
  HEAD:   "text-content-muted bg-surface-border border-surface-border",
};

const TEST_TYPE_LABELS: Record<string, string> = {
  status_code:      "Status Code",
  schema_validation:"Schema",
  response_time:    "Response Time",
  auth:             "Auth Gate",
  error_handling:   "Error Handling",
};

function EndpointResultRow({ result }: { result: any }) {
  const [open, setOpen] = useState(false);
  const isPassed = result.status === "passed";
  const isFailed = result.status === "failed";
  const methodColor = METHOD_COLORS[result.endpoint_method] || METHOD_COLORS.GET;

  return (
    <div className="border-b border-surface-border last:border-0">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-5 py-3 hover:bg-surface-overlay transition-colors text-left"
      >
        {isPassed ? <CheckCircle2 className="w-4 h-4 text-brand-teal flex-shrink-0" />
                  : isFailed ? <XCircle className="w-4 h-4 text-brand-crimson flex-shrink-0" />
                  : <AlertCircle className="w-4 h-4 text-brand-gold flex-shrink-0" />}

        <span className={cn("text-xs font-bold px-2 py-0.5 rounded border", methodColor)}>
          {result.endpoint_method}
        </span>

        <span className="text-xs font-mono text-content-secondary flex-1 truncate">{result.endpoint_path}</span>

        <span className="text-xs text-content-muted bg-surface-border px-2 py-0.5 rounded">
          {TEST_TYPE_LABELS[result.test_type] || result.test_type}
        </span>

        {result.response_time_ms != null && (
          <span className={cn("text-xs", result.response_time_ms > 2000 ? "text-brand-crimson" : "text-content-muted")}>
            {result.response_time_ms}ms
          </span>
        )}

        {result.response_status_code && (
          <span className={cn(
            "text-xs font-mono px-1.5 py-0.5 rounded",
            result.response_status_code < 300 ? "text-brand-teal bg-brand-teal/10"
            : result.response_status_code < 400 ? "text-brand-gold bg-brand-gold/10"
            : "text-brand-crimson bg-brand-crimson/10"
          )}>
            {result.response_status_code}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (isFailed || result.schema_errors?.length > 0) && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-t border-surface-border overflow-hidden"
          >
            <div className="px-5 py-3 space-y-2">
              {result.error_message && (
                <div className="bg-brand-crimson/5 border border-brand-crimson/20 rounded p-2">
                  <p className="text-xs text-brand-crimson">{result.error_message}</p>
                </div>
              )}
              {result.schema_errors?.map((err: string, i: number) => (
                <p key={i} className="text-xs text-content-secondary font-mono">• {err}</p>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function APITestingPage() {
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const [activeTab, setActiveTab] = useState<"url"|"paste">("url");
  const [specUrl, setSpecUrl] = useState("");
  const [specContent, setSpecContent] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [authType, setAuthType] = useState("none");
  const [authToken, setAuthToken] = useState("");
  const [parsedSpec, setParsedSpec] = useState<any>(null);
  const [testResults, setTestResults] = useState<any>(null);

  const parseSpec = useMutation({
    mutationFn: () => apiClient.post("/api-tester/specs/parse", {
      url: activeTab === "url" ? specUrl : undefined,
      content: activeTab === "paste" ? specContent : undefined,
      name: "My API",
    }),
    onSuccess: (res) => {
      setParsedSpec(res.data);
      if (res.data.servers?.[0] && !baseUrl) setBaseUrl(res.data.servers[0]);
      toast.success(`Parsed: ${res.data.endpoint_count} endpoints`);
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Parse failed"),
  });

  const runTests = useMutation({
    mutationFn: () => apiClient.post("/api-tester/tests/run/sync", {
      run_id: `api-${Date.now()}`,
      project_id: "manual",
      org_id: orgId,
      spec_content: activeTab === "url" ? JSON.stringify(parsedSpec?.raw || {}) : specContent,
      base_url: baseUrl,
      auth_config: authType !== "none" ? { type: authType, token: authToken } : null,
    }),
    onSuccess: (res) => {
      setTestResults(res.data);
      const { passed, failed, total } = res.data;
      const passRate = total > 0 ? Math.round(passed / total * 100) : 0;
      toast.success(`Tests complete: ${passed}/${total} passed (${passRate}%)`);
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Test run failed"),
  });

  const results = testResults?.results || [];
  const passedResults = results.filter((r: any) => r.status === "passed");
  const failedResults = results.filter((r: any) => r.status === "failed");

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <Code2 className="w-7 h-7 text-brand-accent" />
          API Testing
        </h1>
        <p className="text-content-muted text-sm mt-1">
          Import an OpenAPI 3.x / Swagger 2.0 / Postman spec and run automated tests
        </p>
      </div>

      {/* Spec import */}
      <div className="glass-card p-6 space-y-4">
        <h2 className="font-semibold text-content-primary">Import API Spec</h2>

        <div className="flex gap-1 p-1 bg-surface-overlay border border-surface-border rounded-lg w-fit">
          {[{id:"url",label:"From URL"},{id:"paste",label:"Paste YAML/JSON"}].map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id as any)}
              className={cn("px-4 py-1.5 rounded text-sm font-medium transition-all",
                activeTab === tab.id ? "bg-brand-accent/15 text-brand-accent border border-brand-accent/25" : "text-content-muted")}>
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "url" ? (
          <div className="flex gap-3">
            <input value={specUrl} onChange={e => setSpecUrl(e.target.value)}
              placeholder="https://petstore.swagger.io/v2/swagger.json"
              className="input-field flex-1 font-mono text-sm" />
            <motion.button whileHover={{scale:1.02}} whileTap={{scale:0.98}}
              onClick={() => parseSpec.mutate()} disabled={parseSpec.isPending || !specUrl}
              className="btn-primary flex items-center gap-2 whitespace-nowrap">
              {parseSpec.isPending ? <><RefreshCw className="w-4 h-4 animate-spin"/>Parsing...</> : <><Link className="w-4 h-4"/>Import</>}
            </motion.button>
          </div>
        ) : (
          <div className="space-y-3">
            <textarea value={specContent} onChange={e => setSpecContent(e.target.value)}
              placeholder="Paste your OpenAPI 3.x YAML or JSON here..."
              rows={8} className="input-field resize-none font-mono text-xs" />
            <motion.button whileHover={{scale:1.02}} whileTap={{scale:0.98}}
              onClick={() => parseSpec.mutate()} disabled={parseSpec.isPending || !specContent}
              className="btn-primary flex items-center gap-2">
              {parseSpec.isPending ? <><RefreshCw className="w-4 h-4 animate-spin"/>Parsing...</> : "Parse Spec"}
            </motion.button>
          </div>
        )}

        {/* Parsed spec summary */}
        {parsedSpec && (
          <motion.div initial={{opacity:0,y:8}} animate={{opacity:1,y:0}}
            className="bg-brand-teal/5 border border-brand-teal/20 rounded-lg p-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <p className="font-semibold text-content-primary">{parsedSpec.title} <span className="text-xs text-content-muted">v{parsedSpec.version}</span></p>
                <div className="flex items-center gap-3 mt-1 text-xs text-content-muted">
                  <span className="font-mono bg-surface-border px-1.5 py-0.5 rounded">{parsedSpec.format}</span>
                  <span>{parsedSpec.endpoint_count} endpoints</span>
                  <span>{parsedSpec.tags?.length || 0} tags</span>
                </div>
              </div>
              <div className="flex flex-wrap gap-1">
                {(parsedSpec.tags || []).slice(0, 5).map((t: string) => (
                  <span key={t} className="text-xs px-2 py-0.5 bg-surface-border rounded-full text-content-muted">{t}</span>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </div>

      {/* Run config */}
      {parsedSpec && (
        <motion.div initial={{opacity:0,y:8}} animate={{opacity:1,y:0}} className="glass-card p-6 space-y-4">
          <h2 className="font-semibold text-content-primary">Test Configuration</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-content-secondary mb-1.5">Base URL</label>
              <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)}
                placeholder="https://api.example.com" className="input-field font-mono text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-content-secondary mb-1.5">Auth</label>
              <div className="flex gap-2">
                <select value={authType} onChange={e => setAuthType(e.target.value)} className="input-field w-32 text-sm">
                  <option value="none">None</option>
                  <option value="bearer">Bearer</option>
                  <option value="api_key">API Key</option>
                  <option value="basic">Basic</option>
                </select>
                {authType !== "none" && (
                  <input value={authToken} onChange={e => setAuthToken(e.target.value)}
                    placeholder="Token / key" className="input-field flex-1 font-mono text-sm" />
                )}
              </div>
            </div>
          </div>
          <motion.button whileHover={{scale:1.01}} whileTap={{scale:0.99}}
            onClick={() => runTests.mutate()} disabled={runTests.isPending || !baseUrl}
            className="btn-primary flex items-center gap-2">
            {runTests.isPending ? <><RefreshCw className="w-4 h-4 animate-spin"/>Running {parsedSpec.endpoint_count} endpoints...</> : <><Play className="w-4 h-4"/>Run API Tests</>}
          </motion.button>
        </motion.div>
      )}

      {/* Results */}
      {testResults && (
        <motion.div initial={{opacity:0,y:8}} animate={{opacity:1,y:0}} className="space-y-4">
          <div className="grid grid-cols-4 gap-4">
            {[
              { label:"Total", value: testResults.total, color:"text-content-primary" },
              { label:"Passed", value: testResults.passed, color:"text-brand-teal" },
              { label:"Failed", value: testResults.failed, color:"text-brand-crimson" },
              { label:"Pass Rate", value: testResults.total ? `${Math.round(testResults.passed/testResults.total*100)}%` : "—", color: testResults.passed===testResults.total ? "text-brand-teal" : "text-brand-gold" },
            ].map(({label,value,color}) => (
              <div key={label} className="glass-card p-4 text-center">
                <div className={cn("text-2xl font-black", color)}>{value}</div>
                <div className="text-xs text-content-muted">{label}</div>
              </div>
            ))}
          </div>

          <div className="glass-card overflow-hidden">
            <div className="px-5 py-3 border-b border-surface-border">
              <h2 className="font-semibold text-content-primary">{results.length} Test Results</h2>
            </div>
            {results.map((r: any, i: number) => <EndpointResultRow key={i} result={r} />)}
          </div>
        </motion.div>
      )}
    </div>
  );
}
