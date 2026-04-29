"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Zap, Send, RefreshCw, User, ChevronRight } from "lucide-react";
import { useAuthStore, useOrgId, useOrgSlug } from "@/store/auth";
import { apiClient } from "@/lib/api";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";

interface Message {
  role: "user" | "assistant";
  content: string;
  tool_calls?: Array<{ tool: string; input: any }>;
  timestamp: Date;
}

const STARTER_PROMPTS = [
  "What's my overall test health today?",
  "Why are my tests failing?",
  "Which projects need attention?",
  "Show me failed deployments this week",
  "What security issues should I fix first?",
  "Analyze failure patterns across my projects",
];

function ToolCallBadge({ tool }: { tool: string }) {
  const labels: Record<string, string> = {
    get_org_stats: "Fetched org stats",
    list_projects: "Listed projects",
    get_project_runs: "Got test runs",
    get_run_failures: "Analyzed failures",
    get_deployments: "Fetched deployments",
    analyze_failure_patterns: "Analyzed patterns",
  };
  return (
    <span className="inline-flex items-center gap-1 text-xs text-brand-cyan bg-brand-cyan/10 border border-brand-cyan/20 px-2 py-0.5 rounded-full mr-1 mb-1">
      <Zap className="w-2.5 h-2.5" />
      {labels[tool] || tool}
    </span>
  );
}

export default function JarviisPage() {
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: "👋 Hi! I'm Jarviis — your AI testing and deployment assistant. I have full access to your test runs, deployments, and security data. What would you like to know?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (text?: string) => {
    const msg = text || input.trim();
    if (!msg || isLoading) return;

    setInput("");
    setSuggestions([]);

    const userMsg: Message = { role: "user", content: msg, timestamp: new Date() };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);

    // Build history for API (exclude first greeting)
    const history = messages
      .slice(1)
      .map(m => ({ role: m.role, content: m.content }));

    try {
      const res = await apiClient.post("/jarviis/chat", {
        message: msg,
        org_id: orgId,
        conversation_history: history,
      });

      const { response, tool_calls, suggestions: newSuggestions } = res.data;
      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: response,
          tool_calls: tool_calls || [],
          timestamp: new Date(),
        },
      ]);
      setSuggestions(newSuggestions || []);
    } catch (err: any) {
      setMessages(prev => [
        ...prev,
        {
          role: "assistant",
          content: "I encountered an error. Make sure `ANTHROPIC_API_KEY` is configured and the Jarviis AI service is running.",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-120px)] max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4 pb-4 border-b border-surface-border">
        <div className="w-10 h-10 rounded-xl bg-brand-accent/10 border border-brand-accent/30 flex items-center justify-center">
          <Zap className="w-5 h-5 text-brand-accent" />
        </div>
        <div>
          <h1 className="font-black text-content-primary">Jarviis</h1>
          <p className="text-xs text-content-muted">AI assistant with access to all your test + deploy data</p>
        </div>
        <div className="ml-auto flex items-center gap-1.5 text-xs text-brand-teal">
          <div className="w-2 h-2 rounded-full bg-brand-teal animate-pulse" />
          Online
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {/* Starter prompts if only greeting shown */}
        {messages.length === 1 && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-2 gap-2 mt-4">
            {STARTER_PROMPTS.map((prompt, i) => (
              <motion.button
                key={prompt}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                whileHover={{ scale: 1.02 }}
                onClick={() => sendMessage(prompt)}
                className="text-left p-3 glass-card border-surface-border hover:border-brand-accent/40 transition-all text-sm text-content-secondary hover:text-content-primary"
              >
                {prompt}
              </motion.button>
            ))}
          </motion.div>
        )}

        {messages.map((msg, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn("flex gap-3", msg.role === "user" && "flex-row-reverse")}
          >
            {/* Avatar */}
            <div className={cn(
              "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-1",
              msg.role === "assistant"
                ? "bg-brand-accent/20 border border-brand-accent/40"
                : "bg-surface-overlay border border-surface-border"
            )}>
              {msg.role === "assistant"
                ? <Zap className="w-4 h-4 text-brand-accent" />
                : <User className="w-4 h-4 text-content-muted" />
              }
            </div>

            {/* Bubble */}
            <div className={cn(
              "flex-1 space-y-2",
              msg.role === "user" && "flex flex-col items-end"
            )}>
              {/* Tool calls */}
              {msg.tool_calls && msg.tool_calls.length > 0 && (
                <div className="flex flex-wrap">
                  {msg.tool_calls.map((tc, j) => (
                    <ToolCallBadge key={j} tool={tc.tool} />
                  ))}
                </div>
              )}

              {/* Message bubble */}
              <div className={cn(
                "rounded-2xl px-4 py-3 max-w-[85%] text-sm",
                msg.role === "assistant"
                  ? "glass-card border-surface-border text-content-primary"
                  : "bg-brand-accent/15 border border-brand-accent/30 text-content-primary"
              )}>
                {msg.role === "assistant" ? (
                  <div className="prose prose-sm prose-invert max-w-none">
                    <ReactMarkdown
                      components={{
                        p: ({ children }) => <p className="text-content-primary text-sm leading-relaxed mb-2 last:mb-0">{children}</p>,
                        strong: ({ children }) => <strong className="text-content-primary font-semibold">{children}</strong>,
                        ul: ({ children }) => <ul className="text-content-secondary text-sm space-y-1 my-2 list-disc list-inside">{children}</ul>,
                        li: ({ children }) => <li className="text-content-secondary">{children}</li>,
                        code: ({ children }) => <code className="text-brand-neon bg-surface-border px-1.5 py-0.5 rounded text-xs font-mono">{children}</code>,
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <p>{msg.content}</p>
                )}
              </div>
            </div>
          </motion.div>
        ))}

        {/* Loading */}
        {isLoading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-brand-accent/20 border border-brand-accent/40 flex items-center justify-center">
              <Zap className="w-4 h-4 text-brand-accent animate-pulse" />
            </div>
            <div className="glass-card px-4 py-3 border-surface-border">
              <div className="flex gap-1.5 items-center">
                {[0,1,2].map(i => (
                  <motion.div
                    key={i}
                    className="w-2 h-2 bg-brand-accent rounded-full"
                    animate={{ scale: [1,1.5,1], opacity: [0.5,1,0.5] }}
                    transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.15 }}
                  />
                ))}
                <span className="text-xs text-content-muted ml-1">Thinking...</span>
              </div>
            </div>
          </div>
        )}

        {/* Follow-up suggestions */}
        {suggestions.length > 0 && !isLoading && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap gap-2 pl-11">
            {suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => sendMessage(s)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-brand-accent/30 text-brand-accent rounded-full hover:bg-brand-accent/10 transition-all"
              >
                {s}
                <ChevronRight className="w-3 h-3" />
              </button>
            ))}
          </motion.div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="mt-4 pt-4 border-t border-surface-border">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && sendMessage()}
            placeholder="Ask Jarviis anything about your tests, deployments, or security..."
            className="input-field flex-1"
            disabled={isLoading}
          />
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => sendMessage()}
            disabled={!input.trim() || isLoading}
            className={cn(
              "w-10 h-10 rounded-lg flex items-center justify-center transition-all",
              input.trim() && !isLoading
                ? "bg-brand-accent text-white hover:bg-brand-accent/80"
                : "bg-surface-border text-content-muted cursor-not-allowed"
            )}
          >
            {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </motion.button>
        </div>
        <p className="text-xs text-content-muted mt-2 text-center">
          Jarviis has real-time access to your test runs, deployments, and security data
        </p>
      </div>
    </div>
  );
}
