"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Settings, Save, User, Building2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient, authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { toast } from "sonner";

export default function SettingsPage() {
  const { user, updateUser } = useAuthStore();
  const [fullName, setFullName] = useState(user?.full_name || "");
  const qc = useQueryClient();

  const updateProfile = useMutation({
    mutationFn: () => authApi.updateMe({ full_name: fullName }),
    onSuccess: (data) => {
      updateUser({ full_name: fullName });
      toast.success("Profile updated");
    },
    onError: () => toast.error("Failed to update profile"),
  });

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <Settings className="w-6 h-6 text-brand-accent" />
          General Settings
        </h1>
        <p className="text-content-muted text-sm mt-1">Manage your profile and account settings</p>
      </div>

      {/* Profile */}
      <div className="glass-card p-6 space-y-4">
        <h2 className="font-semibold text-content-primary flex items-center gap-2">
          <User className="w-4 h-4 text-brand-accent" />
          Profile
        </h2>
        <div>
          <label className="block text-sm font-medium text-content-secondary mb-1.5">Email</label>
          <input value={user?.email || ""} disabled
            className="input-field opacity-60 cursor-not-allowed" />
          <p className="text-xs text-content-muted mt-1">Email cannot be changed after registration</p>
        </div>
        <div>
          <label className="block text-sm font-medium text-content-secondary mb-1.5">Full Name</label>
          <input value={fullName} onChange={e => setFullName(e.target.value)}
            placeholder="Your name" className="input-field" />
        </div>
        <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
          onClick={() => updateProfile.mutate()} disabled={updateProfile.isPending}
          className="btn-primary flex items-center gap-2">
          <Save className="w-4 h-4" />
          {updateProfile.isPending ? "Saving..." : "Save Profile"}
        </motion.button>
      </div>

      {/* Org info */}
      <div className="glass-card p-6 space-y-3">
        <h2 className="font-semibold text-content-primary flex items-center gap-2">
          <Building2 className="w-4 h-4 text-brand-accent" />
          Organization
        </h2>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "Org ID", value: user?.org_id || "—" },
            { label: "Slug", value: user?.org_slug || "—" },
            { label: "Plan", value: user?.plan ? user.plan.charAt(0).toUpperCase() + user.plan.slice(1) : "Free" },
            { label: "Role", value: user?.role ? user.role.charAt(0).toUpperCase() + user.role.slice(1) : "Member" },
          ].map(({ label, value }) => (
            <div key={label} className="bg-surface-overlay rounded-lg p-3 border border-surface-border">
              <p className="text-xs text-content-muted">{label}</p>
              <p className="text-sm font-mono text-content-primary mt-0.5 truncate">{value}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
