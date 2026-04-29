"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Bell, Check, CheckCheck, Zap, XCircle, AlertTriangle, Info, X } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId } from "@/store/auth";
import { cn, formatRelativeTime } from "@/lib/utils";

const EVENT_ICONS: Record<string, any> = {
  "test.failed":           XCircle,
  "test.completed":        Check,
  "deploy.rolled_back":    AlertTriangle,
  "usage.warning_80pct":   AlertTriangle,
  "usage.limit_reached":   XCircle,
  "billing.trial_expired": AlertTriangle,
  "billing.payment_failed":XCircle,
  "security.issue_critical":AlertTriangle,
  "healing.applied":       Zap,
};

const EVENT_COLORS: Record<string, string> = {
  "test.failed":            "text-brand-crimson",
  "test.completed":         "text-brand-teal",
  "deploy.rolled_back":     "text-brand-gold",
  "usage.warning_80pct":    "text-brand-gold",
  "usage.limit_reached":    "text-brand-crimson",
  "billing.trial_expired":  "text-brand-crimson",
  "billing.payment_failed": "text-brand-crimson",
  "security.issue_critical":"text-brand-crimson",
  "healing.applied":        "text-brand-cyan",
};

export function NotificationBell() {
  const orgId = useOrgId();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const { data: unreadData } = useQuery({
    queryKey: ["notif-unread", orgId],
    queryFn: () => apiClient.get(`/notifications/${orgId}/unread-count`).then(r => r.data),
    enabled: !!orgId,
    refetchInterval: 30_000,
  });

  const { data: notifData } = useQuery({
    queryKey: ["notifications", orgId],
    queryFn: () => apiClient.get(`/notifications/${orgId}?limit=20`).then(r => r.data),
    enabled: !!orgId && open,
  });

  const markRead = useMutation({
    mutationFn: (notifId: string) => apiClient.post(`/notifications/${orgId}/mark-read`, { notification_id: notifId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notif-unread", orgId] });
      qc.invalidateQueries({ queryKey: ["notifications", orgId] });
    },
  });

  const unread = unreadData?.unread_count ?? 0;
  const notifications = notifData?.notifications ?? [];

  return (
    <div ref={ref} className="relative">
      <motion.button
        aria-label="Notifications"
        aria-haspopup="true"
        aria-expanded={open}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setOpen(o => !o)}
        className="relative p-2 rounded-lg hover:bg-surface-overlay transition-colors"
      >
        <Bell className="w-5 h-5 text-content-muted hover:text-content-primary transition-colors" />
        {unread > 0 && (
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="absolute -top-0.5 -right-0.5 bg-brand-crimson text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center"
          >
            {unread > 9 ? "9+" : unread}
          </motion.span>
        )}
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            className="absolute right-0 top-full mt-2 w-80 glass-card shadow-2xl z-50 overflow-hidden"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
              <h3 className="font-semibold text-content-primary text-sm">Notifications</h3>
              {unread > 0 && (
                <span className="text-xs text-content-muted">{unread} unread</span>
              )}
            </div>

            <div className="max-h-80 overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="py-8 text-center">
                  <Bell className="w-6 h-6 text-surface-muted mx-auto mb-2" />
                  <p className="text-content-muted text-sm">All caught up!</p>
                </div>
              ) : (
                notifications.map((notif: any) => {
                  const Icon = EVENT_ICONS[notif.event] || Info;
                  const color = EVENT_COLORS[notif.event] || "text-content-muted";
                  const isUnread = !notif.read;

                  return (
                    <motion.div
                      key={notif.id}
                      whileHover={{ x: 2 }}
                      className={cn(
                        "flex items-start gap-3 px-4 py-3 border-b border-surface-border last:border-0 cursor-pointer hover:bg-surface-overlay transition-all",
                        isUnread && "bg-brand-accent/3"
                      )}
                      onClick={() => !notif.read && markRead.mutate(notif.id)}
                    >
                      <div className={cn("mt-0.5 flex-shrink-0", color)}>
                        <Icon className="w-4 h-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className={cn("text-xs leading-relaxed", isUnread ? "text-content-primary" : "text-content-secondary")}>
                          {notif.message}
                        </p>
                        <p className="text-xs text-content-muted mt-0.5">
                          {formatRelativeTime(notif.timestamp)}
                        </p>
                      </div>
                      {isUnread && (
                        <div className="w-2 h-2 bg-brand-accent rounded-full mt-1.5 flex-shrink-0" />
                      )}
                    </motion.div>
                  );
                })
              )}
            </div>

            <div className="px-4 py-2.5 border-t border-surface-border flex items-center justify-between">
              <a href="/notifications" className="text-xs text-brand-accent hover:text-brand-cyan transition-colors">
                View all notifications →
              </a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
