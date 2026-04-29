"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CreditCard, Shield, Users, Plug, Settings, Bell } from "lucide-react";
import { cn } from "@/lib/utils";

const SETTINGS_NAV = [
  { href: "/settings", label: "General", icon: Settings, exact: true },
  { href: "/settings/team", label: "Team", icon: Users },
  { href: "/settings/billing", label: "Billing", icon: CreditCard },
  { href: "/settings/notifications", label: "Notifications", icon: Bell },
  { href: "/settings/sso", label: "Enterprise SSO", icon: Shield },
  { href: "/settings/integrations", label: "Integrations", icon: Plug },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex gap-8">
      {/* Settings sidebar nav */}
      <aside className="w-52 flex-shrink-0">
        <h2 className="text-xs font-semibold text-content-muted uppercase tracking-wider mb-3 px-3">
          Settings
        </h2>
        <nav className="space-y-0.5">
          {SETTINGS_NAV.map(({ href, label, icon: Icon, exact }) => {
            const active = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link key={href} href={href}>
                <div className={cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all",
                  active
                    ? "bg-brand-accent/15 text-brand-accent border border-brand-accent/20"
                    : "text-content-secondary hover:bg-surface-overlay hover:text-content-primary"
                )}>
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  {label}
                </div>
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* Settings content */}
      <main className="flex-1 min-w-0">
        {children}
      </main>
    </div>
  );
}
