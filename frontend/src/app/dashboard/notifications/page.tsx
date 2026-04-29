"use client";

import { motion } from "framer-motion";
import { Bell, Check, CheckCheck, Zap, XCircle, AlertTriangle, Info, Settings } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId } from "@/store/auth";
import { cn, formatRelativeTime } from "@/lib/utils";
import Link from "next/link";

const EVENT_CONFIG: Record<string, { icon: any; color: string; bg: string }> = {
  "test.failed":             { icon: XCircle,       color: "text-brand-crimson", bg: "bg-brand-crimson/10" },
  "test.completed":          { icon: Check,          color: "text-brand-teal",   bg: "bg-brand-teal/10" },
  "deploy.rolled_back":      { icon: AlertTriangle,  color: "text-brand-gold",   bg: "bg-brand-gold/10" },
  "deploy.failed":           { icon: XCircle,        color: "text-brand-crimson", bg: "bg-brand-crimson/10" },
  "security.issue_critical": { icon: AlertTriangle,  color: "text-brand-crimson", bg: "bg-brand-crimson/10" },
  "usage.warning_80pct":     { icon: AlertTriangle,  color: "text-brand-gold",   bg: "bg-brand-gold/10" },
  "usage.limit_reached":     { icon: XCircle,        color: "text-brand-crimson", bg: "bg-brand-crimson/10" },
  "billing.trial_expired":   { icon: AlertTriangle,  color: "text-brand-crimson", bg: "bg-brand-crimson/10" },
  "billing.payment_failed":  { icon: XCircle,        color: "text-brand-crimson", bg: "bg-brand-crimson/10" },
  "billing.plan_changed":    { icon: Zap,            color: "text-brand-accent",  bg: "bg-brand-accent/10" },
  "healing.applied":         { icon: Zap,            color: "text-brand-cyan",    bg: "bg-brand-cyan/10" },
};

export default function NotificationsPage() {
  const orgId = useOrgId();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["notifications-full", orgId],
    queryFn: () => apiClient.get(`/notifications/${orgId}?limit=100`).then(r => r.data),
    enabled: !!orgId,
    refetchInterval: 30_000,
  });

  const markRead = useMutation({
    mutationFn: (notifId: string) =>
      apiClient.post(`/notifications/${orgId}/mark-read`, { notification_id: notifId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications-full", orgId] }),
  });

  const notifications = data?.notifications || [];
  const unread = data?.unread_count || 0;

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
            <Bell className="w-7 h-7 text-brand-accent" />
            Notifications
            {unread > 0 && (
              <span className="bg-brand-crimson text-white text-xs font-bold px-2 py-0.5 rounded-full">
                {unread} unread
              </span>
            )}
          </h1>
          <p className="text-content-muted text-sm mt-1">
            Test results, deployment events, billing, and security alerts
          </p>
        </div>
        <Link href="/settings/notifications">
          <button className="flex items-center gap-2 px-3 py-2 border border-surface-border rounded-lg text-sm text-content-muted hover:text-brand-accent hover:border-brand-accent/40 transition-all">
            <Settings className="w-4 h-4" /> Configure
          </button>
        </Link>
      </div>

      <div className="glass-card overflow-hidden">
        {isLoading ? (
          <div className="p-6 space-y-4">
            {[1,2,3,4,5].map(i => (
              <div key={i} className="flex items-start gap-4 animate-pulse">
                <div className="w-9 h-9 rounded-lg bg-surface-border flex-shrink-0" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-surface-border rounded w-3/4" />
                  <div className="h-3 bg-surface-border rounded w-1/3" />
                </div>
              </div>
            ))}
          </div>
        ) : notifications.length === 0 ? (
          <div className="py-16 text-center">
            <Bell className="w-12 h-12 text-surface-muted mx-auto mb-4" />
            <p className="text-content-primary font-semibold mb-1">All caught up</p>
            <p className="text-content-muted text-sm">
              No notifications yet. They'll appear here when tests complete, deployments run, or billing events occur.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-surface-border">
            {notifications.map((notif: any) => {
              const cfg = EVENT_CONFIG[notif.event] || { icon: Info, color: "text-content-muted", bg: "bg-surface-overlay" };
              const Icon = cfg.icon;
              const isUnread = !notif.read;

              return (
                <motion.div
                  key={notif.id}
                  whileHover={{ x: 2 }}
                  onClick={() => isUnread && markRead.mutate(notif.id)}
                  className={cn(
                    "flex items-start gap-4 px-5 py-4 cursor-pointer hover:bg-surface-overlay transition-all",
                    isUnread && "bg-brand-accent/3 border-l-2 border-brand-accent"
                  )}
                >
                  <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0", cfg.bg)}>
                    <Icon className={cn("w-4 h-4", cfg.color)} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={cn("text-sm leading-relaxed", isUnread ? "text-content-primary font-medium" : "text-content-secondary")}>
                      {notif.message}
                    </p>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-xs text-content-muted">{formatRelativeTime(notif.timestamp)}</span>
                      <span className="text-xs text-surface-muted font-mono">{notif.event}</span>
                    </div>
                  </div>
                  {isUnread && (
                    <div className="w-2 h-2 bg-brand-accent rounded-full mt-2 flex-shrink-0" />
                  )}
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
