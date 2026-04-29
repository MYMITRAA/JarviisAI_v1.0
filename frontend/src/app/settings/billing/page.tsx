"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { CreditCard, CheckCircle2, Zap, ArrowRight, ExternalLink, RefreshCw } from "lucide-react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId, useOrgSlug, usePlan } from "@/store/auth";
import { cn, formatDate } from "@/lib/utils";
import { toast } from "sonner";
import Link from "next/link";

const PLAN_CONFIG = {
  starter:    { color: "text-content-muted", bg: "bg-surface-border",    label: "Starter",    price: "$0/mo" },
  pro:        { color: "text-brand-accent",  bg: "bg-brand-accent/10",   label: "Pro",        price: "$49/mo" },
  team:       { color: "text-brand-teal",    bg: "bg-brand-teal/10",     label: "Team",       price: "$149/mo" },
  enterprise: { color: "text-brand-gold",    bg: "bg-brand-gold/10",     label: "Enterprise", price: "Custom" },
};

export default function BillingPage() {
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const currentPlan = usePlan();
  const planCfg = PLAN_CONFIG[currentPlan as keyof typeof PLAN_CONFIG] || PLAN_CONFIG.starter;

  const { data: invoices, isLoading: loadingInvoices } = useQuery({
    queryKey: ["invoices", orgId],
    queryFn: () => apiClient.get(`/billing/invoices/${stripeCustomerId}`).then(r => r.data),
    enabled: !!orgId,
  });

  const { data: upcoming } = useQuery({
    queryKey: ["upcoming-invoice", orgId],
    queryFn: () => apiClient.get(`/billing/upcoming/${stripeCustomerId}`).then(r => r.data),
    enabled: !!orgId,
  });

  const startCheckout = useMutation({
    mutationFn: (plan: string) =>
      apiClient.post("/billing/checkout", {
        org_id: orgId,
        plan,
        billing_period: "monthly",
        customer_email: user?.email,
      }),
    onSuccess: (res) => {
      if (res.data.checkout_url) {
        window.location.href = res.data.checkout_url;
      } else {
        toast.info("Stripe not configured in this environment");
      }
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Checkout failed"),
  });

  const UPGRADE_PLANS = [
    {
      name: "pro",
      label: "Pro",
      price: "$49/mo",
      highlights: ["20 projects", "2,000 runs/mo", "Deploy engine", "API testing"],
    },
    {
      name: "team",
      label: "Team",
      price: "$149/mo",
      highlights: ["100 projects", "10,000 runs/mo", "COBOL testing", "25 members"],
    },
  ];

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <CreditCard className="w-6 h-6 text-brand-accent" />
          Billing
        </h1>
        <p className="text-content-muted text-sm mt-1">Manage your subscription and payment details</p>
      </div>

      {/* Current plan */}
      <div className="glass-card p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-content-muted uppercase tracking-wider mb-1">Current Plan</p>
            <div className="flex items-center gap-3">
              <span className={cn("text-2xl font-black", planCfg.color)}>{planCfg.label}</span>
              <span className={cn("text-xs px-2.5 py-1 rounded-full font-medium", planCfg.bg, planCfg.color)}>
                {planCfg.price}
              </span>
            </div>
          </div>
          {stripeCustomerId && (
            <button
              onClick={() => openPortal.mutate()}
              disabled={openPortal.isPending}
              className="flex items-center gap-1.5 text-sm text-brand-accent hover:text-brand-cyan transition-colors disabled:opacity-50"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              {openPortal.isPending ? "Opening…" : "Manage billing"}
            </button>
          )}
        </div>

        {upcoming && (
          <div className="mt-4 pt-4 border-t border-surface-border text-sm text-content-muted">
            Next invoice: <strong className="text-content-primary">${upcoming.amount_due}</strong>{" "}
            on {formatDate(upcoming.period_end)}
          </div>
        )}
      </div>

      {/* Upgrade options */}
      {currentPlan === "starter" && (
        <div className="glass-card p-6">
          <h2 className="font-semibold text-content-primary mb-4 flex items-center gap-2">
            <Zap className="w-4 h-4 text-brand-accent" />
            Upgrade your plan
          </h2>
          <div className="grid grid-cols-2 gap-4">
            {UPGRADE_PLANS.map((plan) => (
              <motion.div
                key={plan.name}
                whileHover={{ y: -2 }}
                className="border border-surface-border rounded-xl p-4 hover:border-brand-accent/40 transition-all"
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-bold text-content-primary">{plan.label}</h3>
                  <span className="text-brand-accent font-semibold text-sm">{plan.price}</span>
                </div>
                <ul className="space-y-1.5 mb-4">
                  {plan.highlights.map((h) => (
                    <li key={h} className="flex items-center gap-1.5 text-xs text-content-secondary">
                      <CheckCircle2 className="w-3 h-3 text-brand-teal flex-shrink-0" />
                      {h}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={() => startCheckout.mutate(plan.name)}
                  disabled={startCheckout.isPending}
                  className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium bg-brand-accent/15 text-brand-accent border border-brand-accent/30 hover:bg-brand-accent/25 transition-all"
                >
                  {startCheckout.isPending ? <RefreshCw className="w-3 h-3 animate-spin" /> : null}
                  Upgrade to {plan.label}
                  <ArrowRight className="w-3 h-3" />
                </button>
              </motion.div>
            ))}
          </div>
          <div className="mt-4 text-center">
            <Link href="/pricing" className="text-xs text-brand-accent hover:underline">
              View full pricing comparison →
            </Link>
          </div>
        </div>
      )}

      {/* Invoices */}
      <div className="glass-card overflow-hidden">
        <div className="px-5 py-3 border-b border-surface-border">
          <h2 className="font-semibold text-content-primary">Invoice History</h2>
        </div>
        {loadingInvoices ? (
          <div className="p-6 animate-pulse space-y-3">
            {[1,2,3].map(i => <div key={i} className="h-10 bg-surface-border rounded" />)}
          </div>
        ) : !invoices?.length ? (
          <div className="p-8 text-center text-content-muted text-sm">
            No invoices yet — you'll see billing history here once you upgrade
          </div>
        ) : (
          <div>
            {invoices.map((inv: any) => (
              <div key={inv.id} className="flex items-center gap-4 px-5 py-3.5 border-b border-surface-border last:border-0 hover:bg-surface-overlay transition-colors">
                <div className={cn(
                  "text-xs px-2 py-0.5 rounded-full font-medium",
                  inv.status === "paid" ? "text-brand-teal bg-brand-teal/10" : "text-brand-gold bg-brand-gold/10"
                )}>
                  {inv.status}
                </div>
                <div className="flex-1">
                  <p className="text-sm text-content-primary font-mono">#{inv.number}</p>
                  <p className="text-xs text-content-muted">{formatDate(inv.created)}</p>
                </div>
                <span className="font-semibold text-content-primary text-sm">
                  {inv.currency} ${inv.amount_paid}
                </span>
                {inv.pdf_url && (
                  <a href={inv.pdf_url} target="_blank" rel="noopener noreferrer"
                     className="text-xs text-brand-accent hover:text-brand-cyan transition-colors">
                    PDF
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
