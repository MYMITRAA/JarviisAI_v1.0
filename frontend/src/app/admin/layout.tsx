"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { useAuthStore } from "@/store/auth";
import {
  LayoutDashboard, Users, Building2, CreditCard,
  Settings, Shield, ChevronRight, Zap
} from "lucide-react";
import { cn } from "@/lib/utils";

const ADMIN_NAV = [
  { href: "/admin",         label: "Overview",       icon: LayoutDashboard, exact: true },
  { href: "/admin/users",   label: "Users",          icon: Users },
  { href: "/admin/orgs",    label: "Organizations",  icon: Building2 },
  { href: "/admin/billing", label: "Billing",        icon: CreditCard },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, isAuthenticated } = useAuthStore();

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/auth/login");
      return;
    }
    // Only superadmins and owners can access admin panel
    if (user && user.role !== "owner" && !user.is_superadmin) {
      router.replace("/dashboard");
    }
  }, [isAuthenticated, user, router]);

  if (!isAuthenticated || !user) return null;

  return (
    <div className="min-h-screen bg-brand-primary flex">
      {/* Admin sidebar */}
      <aside className="w-56 flex-shrink-0 border-r border-surface-border bg-surface-raised flex flex-col">
        {/* Logo */}
        <div className="flex items-center gap-2 px-4 py-5 border-b border-surface-border">
          <Shield className="w-5 h-5 text-brand-crimson" />
          <span className="font-black text-content-primary text-sm">JARVIIS ADMIN</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-3 space-y-0.5">
          {ADMIN_NAV.map(({ href, label, icon: Icon, exact }) => {
            const active = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link key={href} href={href}>
                <div className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all",
                  active
                    ? "bg-brand-crimson/15 text-brand-crimson border border-brand-crimson/25"
                    : "text-content-secondary hover:bg-surface-overlay hover:text-content-primary"
                )}>
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  {label}
                </div>
              </Link>
            );
          })}
        </nav>

        {/* Back to app */}
        <div className="p-3 border-t border-surface-border">
          <Link href="/dashboard">
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-content-muted hover:text-content-primary hover:bg-surface-overlay transition-all cursor-pointer">
              <Zap className="w-3.5 h-3.5" />
              Back to App
              <ChevronRight className="w-3 h-3 ml-auto" />
            </div>
          </Link>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 p-8 overflow-y-auto">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
        >
          {children}
        </motion.div>
      </main>
    </div>
  );
}
