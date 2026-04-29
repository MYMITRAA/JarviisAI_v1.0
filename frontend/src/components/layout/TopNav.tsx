"use client";

import { Bell, Search, Plus, Terminal } from "lucide-react";
import { motion } from "framer-motion";
import { useAuthStore } from "@/store/auth";
import Link from "next/link";
import { NotificationBell } from "@/components/ui/NotificationBell";
import { useRouter } from "next/navigation";
import { useState } from "react";

export function TopNav() {
  const { user } = useAuthStore();
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");

  return (
    <header className="h-14 flex items-center justify-between px-6 border-b border-surface-border bg-surface-raised/50 backdrop-blur-sm flex-shrink-0">
      {/* Search */}
      <div className="flex items-center gap-2 bg-surface-overlay border border-surface-border rounded-lg px-3 py-2 w-72 group focus-within:border-brand-accent transition-colors">
        <Search className="w-4 h-4 text-content-muted group-focus-within:text-brand-accent transition-colors" />
        <input
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && searchQuery.trim()) { router.push(`/dashboard/search?q=${encodeURIComponent(searchQuery.trim())}`); setSearchQuery(""); } }}
          placeholder="Search projects, runs..."
          className="bg-transparent text-sm text-content-primary placeholder-content-muted outline-none w-full"
        />
        <kbd className="hidden sm:flex items-center gap-0.5 text-xs text-content-muted bg-surface-border px-1.5 py-0.5 rounded font-mono">
          ⌘K
        </kbd>
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-3">
        {/* New project */}
        <Link href="/projects/new">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="flex items-center gap-2 px-3 py-1.5 bg-brand-accent/10 hover:bg-brand-accent/20 border border-brand-accent/30 hover:border-brand-accent/60 text-brand-accent rounded-lg text-sm font-medium transition-all"
          >
            <Plus className="w-4 h-4" />
            New Project
          </motion.button>
        </Link>

        {/* Terminal */}
        <button
          title="Open terminal"
          className="w-8 h-8 flex items-center justify-center rounded-lg border border-surface-border text-content-muted hover:text-brand-accent hover:border-brand-accent/40 transition-all"
        >
          <Terminal className="w-4 h-4" />
        </button>

        {/* Notifications */}
        <NotificationBell />

        {/* Avatar */}
        <div className="w-8 h-8 rounded-full bg-brand-accent/20 border border-brand-accent/40 flex items-center justify-center cursor-pointer hover:border-brand-accent transition-colors">
          {user?.avatar_url ? (
            <img src={user.avatar_url} alt="" className="w-full h-full rounded-full object-cover" />
          ) : (
            <span className="text-xs font-bold text-brand-accent">
              {user?.full_name?.[0] || user?.email?.[0] || "?"}
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
