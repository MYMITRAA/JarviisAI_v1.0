"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Zap, LayoutDashboard, FolderOpen, Play, Rocket,
  Shield, Settings, ChevronLeft, ChevronRight,
  Terminal, GitBranch, Activity, Users, CreditCard,
  HelpCircle, LogOut, Code2, Search, BarChart3,
  FileText, TrendingUp, ClipboardList, Bell
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore, useOrgId, usePlan } from "@/store/auth";
import { authApi, apiClient } from "@/lib/api";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useFeatureFlags } from "@/lib/flags";

// Compact usage bar for sidebar
function UsageCompact() {
  const orgId = useOrgId();
  const plan = usePlan();
  const flags = useFeatureFlags();
  const { data: usage } = useQuery({
    queryKey: ["usage-compact", orgId],
    queryFn: () => apiClient.get(`/usage/${orgId}?plan=${plan}`).then(r => r.data),
    enabled: !!orgId,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
  const runs = usage?.test_runs;
  if (!runs || runs.unlimited) return null;
  const pct = Math.min(100, runs.percentage || 0);
  const color = runs.over ? "bg-brand-crimson" : runs.warning ? "bg-brand-gold" : "bg-brand-accent";
  return (
    <Link href="/dashboard/usage">
      <div className="px-3 py-2 mb-1 hover:bg-surface-overlay rounded-lg transition-colors cursor-pointer">
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-content-muted">Test runs</span>
          <span className={cn("font-mono text-[10px]", runs.over ? "text-brand-crimson" : runs.warning ? "text-brand-gold" : "text-content-muted")}>
            {runs.current}/{runs.limit}
          </span>
        </div>
        <div className="h-1 bg-surface-border rounded-full overflow-hidden">
          <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
        </div>
      </div>
    </Link>
  );
}

const NAV_ITEMS = [
  {
    group: "WORKSPACE",
    items: [
      { href: "/dashboard",              label: "Command Center",  icon: LayoutDashboard },
      { href: "/projects",               label: "Projects",        icon: FolderOpen },
      { href: "/dashboard/test-runs",    label: "Test Runs",       icon: Play },
      { href: "/dashboard/api-testing",  label: "API Testing",     icon: Code2 },
      { href: "/dashboard/cobol",        label: "COBOL Testing",   icon: Terminal, flag: "cobol_testing" as const },
      { href: "/dashboard/search",                 label: "Search",          icon: Search },
      { href: "/dashboard/mobile",               label: "Mobile Testing",  icon: Smartphone, flag: "mobile_testing" as const },
    ],
  },
  {
    group: "DEPLOY",
    items: [
      { href: "/dashboard/deploy",       label: "Launch Control",  icon: Rocket },
      { href: "/dashboard/deployments",  label: "Deployments",     icon: GitBranch },
      { href: "/dashboard/environments", label: "Environments",    icon: Activity },
      { href: "/dashboard/healing",      label: "Auto-Healing",    icon: Activity, flag: "ai_test_healing" as const },
    ],
  },
  {
    group: "INTELLIGENCE",
    items: [
      { href: "/dashboard/jarviis",      label: "Jarviis AI",      icon: Zap },
      { href: "/dashboard/security",     label: "Security",        icon: Shield },
      { href: "/dashboard/analytics",              label: "Analytics",       icon: BarChart3 },
      { href: "/dashboard/reports",                label: "Reports",         icon: FileText },
    ],
  },
  {
    group: "ACCOUNT",
    items: [
      { href: "/dashboard/usage",                  label: "Usage",           icon: TrendingUp },
      { href: "/dashboard/audit",                  label: "Audit Log",       icon: ClipboardList },
      { href: "/dashboard/notifications", label: "Notifications",  icon: Bell },
      { href: "/settings/billing",       label: "Billing",         icon: CreditCard },
      { href: "/settings/sso",           label: "SSO",             icon: Shield },
      { href: "/settings",               label: "Settings",        icon: Settings },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, refreshToken } = useAuthStore();
  const [collapsed, setCollapsed] = useState(false);

  const handleLogout = async () => {
    try {
      if (refreshToken) await authApi.logout(refreshToken);
    } catch {}
    logout();
    router.push("/auth/login");
    toast.success("Session ended");
  };

  return (
    <motion.aside
      animate={{ width: collapsed ? 64 : 240 }}
      transition={{ duration: 0.25, ease: "easeInOut" }}
      className="relative flex flex-col bg-surface-raised border-r border-surface-border flex-shrink-0 overflow-hidden"
    >
      {/* Logo */}
      <div className={cn("flex items-center p-4 border-b border-surface-border", collapsed ? "justify-center" : "gap-2.5")}>
        <Zap className="w-7 h-7 text-brand-accent flex-shrink-0" />
        <AnimatePresence>
          {!collapsed && (
            <motion.span
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: "auto" }}
              exit={{ opacity: 0, width: 0 }}
              className="text-lg font-black text-gradient overflow-hidden whitespace-nowrap"
            >
              JARVIIS AI
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      {/* Nav items */}
      <nav role="navigation" aria-label="Main navigation" className="flex-1 overflow-y-auto py-3 space-y-4">
        {NAV_ITEMS.map((group) => (
          <div key={group.group}>
            {!collapsed && (
              <p className="px-4 py-1 text-xs font-semibold text-content-muted tracking-widest">
                {group.group}
              </p>
            )}
            <ul className="space-y-0.5 px-2">
              {group.items.map(({ href, label, icon: Icon }) => {
                const active = pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
                const flagKey = item.flag;
                if (flagKey && !flags[flagKey]) return null;
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      className={cn(
                        "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150",
                        active
                          ? "bg-brand-accent/15 text-brand-accent border border-brand-accent/20"
                          : "text-content-secondary hover:bg-surface-overlay hover:text-content-primary",
                        collapsed && "justify-center px-2"
                      )}
                      title={collapsed ? label : undefined}
                    >
                      <Icon className={cn("flex-shrink-0", collapsed ? "w-5 h-5" : "w-4 h-4")} />
                      <AnimatePresence>
                        {!collapsed && (
                          <motion.span
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="whitespace-nowrap overflow-hidden"
                          >
                            {label}
                          </motion.span>
                        )}
                      </AnimatePresence>
                      {active && !collapsed && (
                        <motion.div
                          layoutId="active-indicator"
                          className="ml-auto w-1.5 h-1.5 bg-brand-accent rounded-full"
                        />
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* User footer */}
      <div className="border-t border-surface-border p-3 space-y-1">
        {/* Compact usage bar */}
        {!collapsed && <UsageCompact />}
        {/* Help */}
        <button
          className={cn(
            "flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm text-content-muted hover:text-content-primary hover:bg-surface-overlay transition-all",
            collapsed && "justify-center"
          )}
          title={collapsed ? "Help" : undefined}
        >
          <HelpCircle className="w-4 h-4 flex-shrink-0" />
          {!collapsed && <span>Help & Docs</span>}
        </button>

        {/* User */}
        <div className={cn("flex items-center gap-3 px-3 py-2", collapsed && "justify-center")}>
          <div className="w-7 h-7 rounded-full bg-brand-accent/20 border border-brand-accent/40 flex items-center justify-center flex-shrink-0">
            {user?.avatar_url ? (
              <img src={user.avatar_url} alt="" className="w-full h-full rounded-full object-cover" />
            ) : (
              <span className="text-xs font-bold text-brand-accent">
                {user?.full_name?.[0] || user?.email?.[0] || "?"}
              </span>
            )}
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-content-primary truncate">{user?.full_name || "Developer"}</p>
              <p className="text-xs text-content-muted truncate">{user?.email}</p>
            </div>
          )}
        </div>

        {/* Logout */}
        <button
          onClick={handleLogout}
          className={cn(
            "flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm text-content-muted hover:text-brand-crimson hover:bg-brand-crimson/10 transition-all",
            collapsed && "justify-center"
          )}
          title={collapsed ? "Logout" : undefined}
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          {!collapsed && <span>Sign Out</span>}
        </button>
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute top-1/2 -right-3 -translate-y-1/2 w-6 h-6 bg-surface-overlay border border-surface-border rounded-full flex items-center justify-center text-content-muted hover:text-brand-accent hover:border-brand-accent transition-all z-10"
      >
        {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
      </button>
    </motion.aside>
  );
}
