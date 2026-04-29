"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Smartphone, Apple, Play, Shield, RefreshCw, Zap } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId } from "@/store/auth";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const DEVICE_TYPES = [
  { id: "android", label: "Android",   icon: Smartphone, color: "text-brand-teal",   desc: "AWS Device Farm — real devices" },
  { id: "ios",     label: "iOS",       icon: Apple,      color: "text-brand-accent", desc: "BrowserStack App Automate"      },
];

export default function MobilePage() {
  const orgId = useOrgId();
  const [platform, setPlatform] = useState<"android" | "ios">("android");
  const [appUrl, setAppUrl] = useState("");
  const [testType, setTestType] = useState("functional");

  const runMutation = useMutation({
    mutationFn: () => apiClient.post(`/mobile/run`, {
      org_id: orgId,
      platform,
      app_url: appUrl,
      test_type: testType,
    }),
    onSuccess: (res: any) => toast.success(`Mobile test started: ${res.data?.job_id || "queued"}`),
    onError: () => toast.error("Failed to start mobile test"),
  });

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <Smartphone className="w-7 h-7 text-brand-accent" /> Mobile Testing
        </h1>
        <p className="text-content-muted text-sm mt-1">
          AI-generated tests for Android and iOS applications on real devices
        </p>
      </div>

      {/* Platform select */}
      <div className="grid grid-cols-2 gap-4">
        {DEVICE_TYPES.map(({ id, label, icon: Icon, color, desc }) => (
          <motion.button
            key={id}
            whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }}
            onClick={() => setPlatform(id as "android" | "ios")}
            className={cn(
              "glass-card p-5 text-left transition-all",
              platform === id ? "border-brand-accent/40 bg-brand-accent/5" : ""
            )}
          >
            <div className="flex items-center gap-3 mb-2">
              <Icon className={cn("w-6 h-6", color)} />
              <span className="font-semibold text-content-primary">{label}</span>
              {platform === id && (
                <span className="ml-auto text-xs px-2 py-0.5 bg-brand-accent/15 text-brand-accent rounded-full border border-brand-accent/25">
                  Selected
                </span>
              )}
            </div>
            <p className="text-xs text-content-muted">{desc}</p>
          </motion.button>
        ))}
      </div>

      {/* Test config */}
      <div className="glass-card p-6 space-y-4">
        <h2 className="font-semibold text-content-primary">Configure Test</h2>

        <div>
          <label className="text-sm font-medium text-content-secondary mb-1.5 block">
            {platform === "android" ? "APK URL" : "IPA URL"}
          </label>
          <input
            value={appUrl}
            onChange={e => setAppUrl(e.target.value)}
            placeholder={platform === "android" ? "https://example.com/app.apk" : "https://example.com/app.ipa"}
            className="input-field font-mono text-sm"
          />
          <p className="text-xs text-content-muted mt-1">
            Publicly accessible URL to your {platform === "android" ? "Android APK" : "iOS IPA"} file
          </p>
        </div>

        <div>
          <label className="text-sm font-medium text-content-secondary mb-1.5 block">Test Type</label>
          <div className="flex gap-2">
            {["functional", "ui", "performance", "security"].map(t => (
              <button
                key={t}
                onClick={() => setTestType(t)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-medium border capitalize transition-all",
                  testType === t
                    ? "border-brand-accent bg-brand-accent/10 text-brand-accent"
                    : "border-surface-border text-content-muted hover:border-surface-muted"
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <motion.button
          whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
          onClick={() => runMutation.mutate()}
          disabled={!appUrl || runMutation.isPending}
          className="btn-primary flex items-center gap-2 w-full justify-center py-3"
        >
          {runMutation.isPending ? (
            <><RefreshCw className="w-4 h-4 animate-spin" /> Starting test…</>
          ) : (
            <><Play className="w-4 h-4" /> Run Mobile Tests</>
          )}
        </motion.button>
      </div>

      {/* Features */}
      <div className="glass-card p-6">
        <h2 className="font-semibold text-content-primary mb-4 flex items-center gap-2">
          <Zap className="w-4 h-4 text-brand-accent" /> What's Tested
        </h2>
        <div className="grid grid-cols-2 gap-3">
          {[
            "UI element detection & interaction",
            "Screen transition flows",
            "Form validation & input handling",
            "Network request interception",
            "Crash detection & stack traces",
            "Performance & startup time",
            "Accessibility compliance",
            "Device rotation handling",
          ].map(item => (
            <div key={item} className="flex items-center gap-2 text-sm text-content-secondary">
              <div className="w-1.5 h-1.5 bg-brand-teal rounded-full flex-shrink-0" />
              {item}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
