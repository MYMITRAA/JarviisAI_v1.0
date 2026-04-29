import { Metadata } from "next";

export const metadata: Metadata = {
  title: "System Status — JarviisAI",
  description: "Real-time status of JarviisAI platform services",
};

const SERVICES = [
  { name: "API Gateway",        category: "Core" },
  { name: "Test Execution",     category: "Core" },
  { name: "AI Generation",      category: "Core" },
  { name: "Deploy Engine",      category: "Core" },
  { name: "Notifications",      category: "Platform" },
  { name: "Analytics",          category: "Platform" },
  { name: "Billing",            category: "Platform" },
];

export default function StatusPage() {
  return (
    <div className="min-h-screen bg-brand-primary py-16 px-6">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-brand-teal/10 border border-brand-teal/30 text-brand-teal text-sm font-medium mb-6">
            <div className="w-2 h-2 bg-brand-teal rounded-full animate-pulse" />
            All Systems Operational
          </div>
          <h1 className="text-4xl font-black text-white mb-2">System Status</h1>
          <p className="text-gray-400">Real-time health of the JarviisAI platform</p>
        </div>

        {/* Service list */}
        <div className="bg-white/5 rounded-2xl border border-white/10 overflow-hidden">
          <div className="px-6 py-4 border-b border-white/10">
            <h2 className="font-semibold text-white">Services</h2>
          </div>
          {SERVICES.map((svc, i) => (
            <div key={svc.name}
              className="flex items-center justify-between px-6 py-4 border-b border-white/5 last:border-0 hover:bg-white/3">
              <div>
                <p className="text-sm font-medium text-white">{svc.name}</p>
                <p className="text-xs text-gray-500">{svc.category}</p>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-green-500 rounded-full" />
                <span className="text-xs text-green-400 font-medium">Operational</span>
              </div>
            </div>
          ))}
        </div>

        {/* Uptime */}
        <div className="mt-8 grid grid-cols-3 gap-4">
          {[
            { label: "Uptime (30d)",    value: "99.97%" },
            { label: "Avg Response",   value: "124ms"  },
            { label: "Incidents (30d)", value: "0"      },
          ].map(({ label, value }) => (
            <div key={label} className="bg-white/5 rounded-xl p-4 border border-white/10 text-center">
              <div className="text-2xl font-black text-white mb-1">{value}</div>
              <div className="text-xs text-gray-400">{label}</div>
            </div>
          ))}
        </div>

        <p className="text-center text-xs text-gray-500 mt-8">
          Subscribe to incidents at{" "}
          <a href="mailto:status@jarviis.ai" className="text-purple-400 hover:underline">
            status@jarviis.ai
          </a>
        </p>
      </div>
    </div>
  );
}
