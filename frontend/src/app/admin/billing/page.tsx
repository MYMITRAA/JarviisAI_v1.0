"use client";

import { CreditCard, TrendingUp, Users, Zap } from "lucide-react";

const PLAN_CONFIG = [
  { plan: "Enterprise", price: "Custom", color: "text-brand-gold",    bg: "bg-brand-gold/10" },
  { plan: "Team",       price: "$149/mo", color: "text-brand-teal",   bg: "bg-brand-teal/10" },
  { plan: "Pro",        price: "$49/mo",  color: "text-brand-accent",  bg: "bg-brand-accent/10" },
  { plan: "Starter",    price: "Free",    color: "text-content-muted", bg: "bg-surface-border" },
];

export default function AdminBillingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <CreditCard className="w-7 h-7 text-brand-accent" />
          Billing Overview
        </h1>
        <p className="text-content-muted text-sm mt-1">Revenue and subscription metrics</p>
      </div>

      <div className="glass-card p-8 text-center border-dashed border-surface-muted">
        <CreditCard className="w-12 h-12 text-surface-muted mx-auto mb-4" />
        <h2 className="font-semibold text-content-primary mb-2">Stripe Dashboard</h2>
        <p className="text-content-muted text-sm mb-4 max-w-md mx-auto">
          Detailed billing analytics, MRR, churn, and customer LTV are available in your Stripe dashboard.
          This page shows a summary view.
        </p>
        <a
          href="https://dashboard.stripe.com"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-4 py-2 bg-brand-accent text-white rounded-lg text-sm font-medium hover:bg-brand-accent/80 transition-all"
        >
          Open Stripe Dashboard →
        </a>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {PLAN_CONFIG.map(({ plan, price, color, bg }) => (
          <div key={plan} className="glass-card p-5">
            <div className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-bold mb-3 ${bg} ${color}`}>
              {plan}
            </div>
            <div className={`text-2xl font-black ${color}`}>{price}</div>
            <div className="text-xs text-content-muted mt-1">per organization / month</div>
          </div>
        ))}
      </div>
    </div>
  );
}
