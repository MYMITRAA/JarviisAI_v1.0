"use client";

import { motion } from "framer-motion";
import { Plug, Github, Slack, Globe, Check, ExternalLink, ArrowRight } from "lucide-react";
import { useAuthStore } from "@/store/auth";
import Link from "next/link";

const INTEGRATIONS = [
  {
    id: "github",
    name: "GitHub",
    icon: Github,
    color: "text-content-primary",
    bg: "bg-surface-overlay",
    description: "Trigger test runs on push, pull requests, and deployments. Post results as commit status checks.",
    features: ["Auto-run on push", "PR status checks", "Branch protection", "Deployment triggers"],
    connected: false,
    href: "/settings/integrations/github",
    category: "CI/CD",
  },
  {
    id: "slack",
    name: "Slack",
    icon: Slack,
    color: "text-[#4A154B]",
    bg: "bg-purple-900/10",
    description: "Get instant alerts for test failures, deployments, and security issues directly in your Slack channels.",
    features: ["Test failure alerts", "Deploy notifications", "Usage warnings", "Security alerts"],
    connected: false,
    href: "/settings/notifications",
    category: "Notifications",
  },
  {
    id: "teams",
    name: "Microsoft Teams",
    icon: () => <span className="text-[#5558AF] font-bold text-base">M</span>,
    color: "text-[#5558AF]",
    bg: "bg-blue-900/10",
    description: "Deliver JarviisAI alerts to Microsoft Teams channels.",
    features: ["Webhook notifications", "Test results", "Deployment status"],
    connected: false,
    href: "/settings/notifications",
    category: "Notifications",
  },
  {
    id: "webhook",
    name: "Custom Webhooks",
    icon: Globe,
    color: "text-brand-gold",
    bg: "bg-brand-gold/10",
    description: "Send JarviisAI events to any HTTP endpoint. Build custom integrations with your own tools.",
    features: ["All event types", "Signed payloads", "Retry on failure", "Custom headers"],
    connected: false,
    href: "/settings/notifications",
    category: "Notifications",
  },
];

const CATEGORIES = [...new Set(INTEGRATIONS.map(i => i.category))];

export default function IntegrationsPage() {
  const { user } = useAuthStore();

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <Plug className="w-6 h-6 text-brand-accent" />
          Integrations
        </h1>
        <p className="text-content-muted text-sm mt-1">
          Connect JarviisAI to your existing tools and workflows
        </p>
      </div>

      {CATEGORIES.map(category => (
        <div key={category}>
          <h2 className="text-xs font-semibold text-content-muted uppercase tracking-wider mb-3">{category}</h2>
          <div className="space-y-3">
            {INTEGRATIONS.filter(i => i.category === category).map((integration, idx) => (
              <motion.div
                key={integration.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="glass-card p-5"
              >
                <div className="flex items-start gap-4">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 border border-surface-border ${integration.bg}`}>
                    {typeof integration.icon === 'function'
                      ? <integration.icon />
                      : <integration.icon className={`w-6 h-6 ${integration.color}`} />
                    }
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-1">
                      <h3 className="font-semibold text-content-primary">{integration.name}</h3>
                      {integration.connected && (
                        <span className="flex items-center gap-1 text-xs text-brand-teal bg-brand-teal/10 px-2 py-0.5 rounded-full">
                          <Check className="w-3 h-3" /> Connected
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-content-muted mb-3">{integration.description}</p>
                    <div className="flex flex-wrap gap-2 mb-4">
                      {integration.features.map(f => (
                        <span key={f} className="text-xs px-2 py-0.5 bg-surface-border rounded-full text-content-muted">
                          {f}
                        </span>
                      ))}
                    </div>
                    <Link href={integration.href}>
                      <motion.button
                        whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                        className="flex items-center gap-2 px-4 py-2 border border-brand-accent/30 text-brand-accent text-sm rounded-lg hover:bg-brand-accent/10 transition-all"
                      >
                        {integration.connected ? "Configure" : "Connect"} <ArrowRight className="w-3.5 h-3.5" />
                      </motion.button>
                    </Link>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
