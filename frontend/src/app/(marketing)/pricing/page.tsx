import Link from "next/link";
import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pricing — JarviisAI",
  description: "Start free. Scale as you grow. Cancel anytime.",
};

const PLANS = [
  {
    name: "Starter",
    price: 0,
    period: "forever",
    description: "For indie developers shipping solo projects",
    highlight: false,
    cta: "Start Free",
    href: "/auth/register",
    features: [
      "3 projects",
      "100 test runs / month",
      "10 deployments / month",
      "20 AI generations / month",
      "5 security scans / month",
      "AI test generation (20/mo)",
      "Basic web testing",
      "1 environment",
      "Community support",
    ],
    limits: [
      "No API testing",
      "No team members",
      "No deploy engine",
      "No COBOL testing",
    ],
  },
  {
    name: "Pro",
    price: 49,
    period: "per month",
    description: "For solo developers and freelancers shipping production apps",
    highlight: true,
    badge: "Most Popular",
    cta: "Start 14-Day Trial",
    href: "/auth/register?plan=pro",
    features: [
      "20 projects",
      "2,000 test runs / month",
      "200 deployments / month",
      "500 AI generations / month",
      "50 security scans / month",
      "AI test generation (500/mo)",
      "Web + API testing",
      "5 environments",
      "Deploy engine (rolling, blue-green)",
      "Self-healing tests",
      "Security scanning (50/mo)",
      "Priority support",
      "GitHub integration",
    ],
  },
  {
    name: "Team",
    price: 149,
    period: "per month",
    description: "For fast-growing teams shipping multiple products",
    highlight: false,
    cta: "Start 14-Day Trial",
    href: "/auth/register?plan=team",
    features: [
      "100 projects",
      "10,000 test runs / month",
      "1,000 deployments / month",
      "2,000 AI generations / month",
      "200 security scans / month",
      "AI test generation (2,000/mo)",
      "Web + API + COBOL testing",
      "20 environments",
      "All deploy strategies",
      "Self-healing + visual regression",
      "Security scanning (200/mo)",
      "25 team members",
      "Jarviis AI assistant",
      "Priority support + SLA",
    ],
  },
  {
    name: "Enterprise",
    price: null,
    period: "custom",
    description: "For large organizations with compliance and scale requirements",
    highlight: false,
    cta: "Contact Sales",
    href: "/contact",
    features: [
      "Unlimited everything",
      "Enterprise SSO (SAML/OIDC)",
      "Mainframe/COBOL testing",
      "On-premise deployment option",
      "Dedicated support engineer",
      "Custom SLAs",
      "Audit logs & compliance",
      "Custom AI model fine-tuning",
      "Volume pricing",
    ],
  },
];

export default function PricingPage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white pt-24 pb-24 px-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="text-5xl font-black mb-4">
            Simple pricing.<br />
            <span style={{ background: "linear-gradient(135deg, #6d28d9, #06b6d4)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              Extraordinary results.
            </span>
          </h1>
          <p className="text-slate-400 text-lg max-w-xl mx-auto">
            Start free. Upgrade when you need more. Cancel anytime.
            No surprise bills.
          </p>
        </div>

        {/* Plan cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-16">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={`relative rounded-2xl p-6 border transition-all ${
                plan.highlight
                  ? "border-purple-500 bg-purple-950/30"
                  : "border-slate-700/60 bg-slate-900/60"
              }`}
            >
              {plan.badge && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-purple-600 rounded-full text-xs font-bold whitespace-nowrap">
                  {plan.badge}
                </div>
              )}

              <div className="mb-5">
                <h2 className="text-lg font-bold text-white">{plan.name}</h2>
                <p className="text-slate-400 text-sm mt-1">{plan.description}</p>
              </div>

              <div className="mb-6">
                {plan.price !== null ? (
                  <div className="flex items-baseline gap-1">
                    <span className="text-4xl font-black">${plan.price}</span>
                    <span className="text-slate-400 text-sm">/ {plan.period}</span>
                  </div>
                ) : (
                  <div className="text-2xl font-black text-purple-400">Custom</div>
                )}
              </div>

              <Link href={plan.href}>
                <button
                  className={`w-full py-3 rounded-xl text-sm font-bold transition-all mb-6 ${
                    plan.highlight
                      ? "text-white hover:opacity-90"
                      : "border border-slate-600 text-slate-300 hover:border-slate-400 hover:text-white"
                  }`}
                  style={plan.highlight ? { background: "linear-gradient(135deg, #6d28d9, #5b21b6)" } : {}}
                >
                  {plan.cta}
                </button>
              </Link>

              <ul className="space-y-2.5">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm text-slate-300">
                    <span className="text-green-400 mt-0.5 flex-shrink-0">✓</span>
                    {f}
                  </li>
                ))}
                {plan.limits?.map((l) => (
                  <li key={l} className="flex items-start gap-2 text-sm text-slate-500">
                    <span className="mt-0.5 flex-shrink-0">✗</span>
                    {l}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* FAQ */}
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl font-black text-center mb-8">Frequently asked questions</h2>
          <div className="space-y-6">
            {[
              {
                q: "What counts as a test run?",
                a: "One test run = one full autonomous testing session for a project. This includes crawling, AI generation, and executing all generated tests. A typical run generates 20-100 test cases.",
              },
              {
                q: "Do I need to write any tests myself?",
                a: "No. JarviisAI's AI generates tests automatically from crawling your application. You can optionally add custom test cases on top of the AI-generated ones.",
              },
              {
                q: "What happens when I exceed my limit?",
                a: "We'll notify you when you're at 80% of your limit. You won't be cut off mid-test. We'll ask you to upgrade before starting new runs once you've hit the limit.",
              },
              {
                q: "Can I test apps that require login?",
                a: "Yes. You can configure authentication credentials (email/password, OAuth, API keys) in project settings. JarviisAI logs in before crawling and testing.",
              },
              {
                q: "Is there a self-hosted option?",
                a: "Enterprise plans include an on-premise deployment option. All services run on Docker Compose and can be deployed to your own infrastructure.",
              },
            ].map(({ q, a }) => (
              <div key={q} className="border border-slate-700/60 rounded-xl p-5">
                <h3 className="font-semibold text-white mb-2">{q}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{a}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
