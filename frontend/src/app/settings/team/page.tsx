"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Users, Mail, Plus, Trash2, Crown, Shield, User, RefreshCw } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId, useRole } from "@/store/auth";
import { cn, formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

const ROLE_CONFIG: Record<string, { icon: any; color: string; label: string }> = {
  owner:  { icon: Crown,  color: "text-brand-gold",    label: "Owner"  },
  admin:  { icon: Shield, color: "text-brand-accent",  label: "Admin"  },
  member: { icon: User,   color: "text-content-muted", label: "Member" },
};

export default function TeamPage() {
  const orgId = useOrgId();
  const currentRole = useRole();
  const qc = useQueryClient();
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");

  const canManage = currentRole === "owner" || currentRole === "admin";

  const { data, isLoading } = useQuery({
    queryKey: ["team-members", orgId],
    queryFn: () => apiClient.get(`/organizations/${orgId}/members`).then(r => r.data),
    enabled: !!orgId,
  });

  const members = data?.members || [];

  const inviteMutation = useMutation({
    mutationFn: () => apiClient.post(`/organizations/${orgId}/invites`, {
      email: inviteEmail,
      role: inviteRole,
    }),
    onSuccess: () => {
      toast.success(`Invitation sent to ${inviteEmail}`);
      setInviteEmail("");
      qc.invalidateQueries({ queryKey: ["team-members", orgId] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Failed to send invite"),
  });

  const removeMutation = useMutation({
    mutationFn: (userId: string) => apiClient.delete(`/organizations/${orgId}/members/${userId}`),
    onSuccess: () => {
      toast.success("Member removed");
      qc.invalidateQueries({ queryKey: ["team-members", orgId] });
    },
    onError: () => toast.error("Failed to remove member"),
  });

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <Users className="w-6 h-6 text-brand-accent" /> Team
        </h1>
        <p className="text-content-muted text-sm mt-1">
          Manage your organization's members and permissions
        </p>
      </div>

      {/* Invite form */}
      {canManage && (
        <div className="glass-card p-5">
          <h2 className="font-semibold text-content-primary mb-4 flex items-center gap-2">
            <Mail className="w-4 h-4 text-brand-accent" /> Invite Team Member
          </h2>
          <div className="flex items-center gap-3">
            <input
              type="email"
              value={inviteEmail}
              onChange={e => setInviteEmail(e.target.value)}
              onKeyDown={e => e.key === "Enter" && inviteEmail && inviteMutation.mutate()}
              placeholder="colleague@company.com"
              className="input-field flex-1"
            />
            <select
              value={inviteRole}
              onChange={e => setInviteRole(e.target.value)}
              className="input-field w-32"
            >
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
            <motion.button
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
              onClick={() => inviteEmail && inviteMutation.mutate()}
              disabled={!inviteEmail || inviteMutation.isPending}
              className="btn-primary flex items-center gap-2 whitespace-nowrap"
            >
              <Plus className="w-4 h-4" />
              {inviteMutation.isPending ? "Sending…" : "Invite"}
            </motion.button>
          </div>
          <p className="text-xs text-content-muted mt-2">
            Members can view and run tests. Admins can manage projects and settings. Only Owners can invite Admins.
          </p>
        </div>
      )}

      {/* Member list */}
      <div className="glass-card overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-surface-border">
          <h2 className="font-semibold text-content-primary">
            Members <span className="text-content-muted font-normal text-sm">({members.length})</span>
          </h2>
        </div>

        {isLoading ? (
          <div className="p-6 space-y-4">
            {[1,2,3].map(i => (
              <div key={i} className="flex items-center gap-4 animate-pulse">
                <div className="w-10 h-10 rounded-full bg-surface-border" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-surface-border rounded w-1/3" />
                  <div className="h-3 bg-surface-border rounded w-1/4" />
                </div>
              </div>
            ))}
          </div>
        ) : members.length === 0 ? (
          <div className="py-12 text-center">
            <Users className="w-10 h-10 text-surface-muted mx-auto mb-3" />
            <p className="text-content-muted text-sm">No members yet. Invite your team above.</p>
          </div>
        ) : (
          <div className="divide-y divide-surface-border">
            {members.map((member: any) => {
              const roleCfg = ROLE_CONFIG[member.role] || ROLE_CONFIG.member;
              const RoleIcon = roleCfg.icon;

              return (
                <div key={member.id} className="flex items-center gap-4 px-5 py-4">
                  <div className="w-10 h-10 rounded-full bg-brand-accent/20 border border-brand-accent/30 flex items-center justify-center flex-shrink-0">
                    <span className="text-sm font-bold text-brand-accent">
                      {member.full_name?.[0] || member.email?.[0] || "?"}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-content-primary">
                      {member.full_name || member.email}
                    </p>
                    <p className="text-xs text-content-muted">{member.email}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={cn("flex items-center gap-1.5 text-xs font-medium", roleCfg.color)}>
                      <RoleIcon className="w-3.5 h-3.5" /> {roleCfg.label}
                    </span>
                    {canManage && member.role !== "owner" && (
                      <motion.button
                        whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }}
                        onClick={() => removeMutation.mutate(member.user_id)}
                        className="p-1.5 rounded text-content-muted hover:text-brand-crimson hover:bg-brand-crimson/10 transition-all"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </motion.button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
