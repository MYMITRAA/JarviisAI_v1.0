"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Bell, Slack, Mail, Globe, Send, RefreshCw, Check } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId } from "@/store/auth";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

export default function NotificationsSettingsPage() {
  const orgId = useOrgId();
  const qc = useQueryClient();
  const [slackUrl, setSlackUrl] = useState("");
  const [teamsUrl, setTeamsUrl] = useState("");
  const [email, setEmail] = useState("");
  const [webhook, setWebhook] = useState("");
  const [testing, setTesting] = useState(false);

  const { data: config } = useQuery({
    queryKey: ["notif-config", orgId],
    queryFn: () => apiClient.get(`/notifications/${orgId}/config`).then(r => r.data),
    enabled: !!orgId,
  });

  // Populate form when config loads (RQ v5: onSuccess removed from useQuery)
  useEffect(() => {
    if (config) {
      if ((config as any).slack_webhook_url) setSlackUrl((config as any).slack_webhook_url);
      if ((config as any).teams_webhook_url) setTeamsUrl((config as any).teams_webhook_url);
      if ((config as any).notification_email) setEmail((config as any).notification_email);
    }
  }, [config]);

  const save = useMutation({
    mutationFn: () => apiClient.post(`/notifications/${orgId}/config`, {
      slack_webhook_url: slackUrl || null,
      teams_webhook_url: teamsUrl || null,
      notification_email: email || null,
      custom_webhooks: webhook ? [webhook] : [],
      enabled_events: [],
    }),
    onSuccess: () => {
      toast.success("Notification settings saved");
      qc.invalidateQueries({ queryKey: ["notif-config", orgId] });
    },
    onError: () => toast.error("Failed to save"),
  });

  const testNotification = async () => {
    setTesting(true);
    try {
      await apiClient.post(`/notifications/test-send?org_id=${orgId}&event_type=test.failed`);
      toast.success("Test notification sent! Check your configured channels.");
    } catch {
      toast.error("Test send failed");
    } finally {
      setTesting(false);
    }
  };

  const EVENTS_INFO = [
    { event: "test.failed",           label: "Test Run Failed",        channels: "Slack, Email, In-app" },
    { event: "test.completed",        label: "Test Run Passed",         channels: "In-app" },
    { event: "deploy.rolled_back",    label: "Deployment Rolled Back",  channels: "Slack, Email, In-app" },
    { event: "security.issue_critical",label:"Critical Security Issue", channels: "Slack, Email, In-app" },
    { event: "usage.warning_80pct",   label: "80% Plan Limit Used",     channels: "Email, In-app" },
    { event: "usage.limit_reached",   label: "Plan Limit Reached",      channels: "Email, In-app" },
    { event: "billing.trial_expired", label: "2-Day Trial Ended",       channels: "Email, In-app" },
    { event: "billing.payment_failed",label: "Payment Failed",          channels: "Email, In-app" },
    { event: "healing.applied",       label: "Auto-Healing Applied",    channels: "In-app" },
  ];

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <Bell className="w-6 h-6 text-brand-accent" />
          Notifications
        </h1>
        <p className="text-content-muted text-sm mt-1">
          Configure where to receive alerts for test failures, deployments, and billing events
        </p>
      </div>

      {/* Channels */}
      <div className="glass-card p-6 space-y-5">
        <h2 className="font-semibold text-content-primary">Notification Channels</h2>

        {/* Slack */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-content-secondary">
            <Slack className="w-4 h-4 text-[#4A154B]" />
            Slack Webhook URL
          </label>
          <input value={slackUrl} onChange={e => setSlackUrl(e.target.value)}
            placeholder="https://hooks.slack.com/services/..."
            className="input-field font-mono text-sm" />
          <p className="text-xs text-content-muted">
            Create an Incoming Webhook in your Slack workspace: Apps → Incoming Webhooks
          </p>
        </div>

        {/* Email */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-content-secondary">
            <Mail className="w-4 h-4 text-brand-cyan" />
            Notification Email
          </label>
          <input value={email} onChange={e => setEmail(e.target.value)}
            type="email" placeholder="devops@yourcompany.com"
            className="input-field text-sm" />
        </div>

        {/* Teams */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-content-secondary">
            <span className="text-[#5558AF] font-bold text-xs">M</span>
            Microsoft Teams Webhook URL
          </label>
          <input value={teamsUrl} onChange={e => setTeamsUrl(e.target.value)}
            placeholder="https://yourorg.webhook.office.com/..."
            className="input-field font-mono text-sm" />
        </div>

        {/* Custom webhook */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-content-secondary">
            <Globe className="w-4 h-4 text-brand-gold" />
            Custom Webhook URL
          </label>
          <input value={webhook} onChange={e => setWebhook(e.target.value)}
            placeholder="https://your-service.com/webhooks/jarviis"
            className="input-field font-mono text-sm" />
          <p className="text-xs text-content-muted">
            Receives POST with JSON: {`{event, payload, timestamp, source}`}
          </p>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
            onClick={() => save.mutate()} disabled={save.isPending}
            className="btn-primary flex items-center gap-2">
            {save.isPending ? <><RefreshCw className="w-4 h-4 animate-spin" />Saving...</> : <><Check className="w-4 h-4" />Save Config</>}
          </motion.button>
          <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
            onClick={testNotification} disabled={testing}
            className="btn-secondary flex items-center gap-2">
            {testing ? <><RefreshCw className="w-4 h-4 animate-spin" />Sending...</> : <><Send className="w-4 h-4" />Send Test</>}
          </motion.button>
        </div>
      </div>

      {/* Events table */}
      <div className="glass-card overflow-hidden">
        <div className="px-5 py-3 border-b border-surface-border">
          <h2 className="font-semibold text-content-primary">Event → Channel Mapping</h2>
          <p className="text-xs text-content-muted mt-0.5">These are the default routing rules. Enterprise plans get custom routing.</p>
        </div>
        <div className="divide-y divide-surface-border">
          {EVENTS_INFO.map(evt => (
            <div key={evt.event} className="flex items-center gap-4 px-5 py-3">
              <div className="flex-1">
                <p className="text-sm text-content-primary">{evt.label}</p>
                <p className="text-xs font-mono text-content-muted">{evt.event}</p>
              </div>
              <span className="text-xs text-content-muted text-right">{evt.channels}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
