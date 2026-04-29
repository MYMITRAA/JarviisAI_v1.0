import Link from "next/link";
import { Metadata } from "next";

export const metadata: Metadata = {
  title: "JarviisAI — Autonomous Testing & Deployment Platform",
  description: "AI-native platform that autonomously tests your code, deploys it, and heals production issues. Zero manual QA. Zero testers required.",
};

// ── Hero section ───────────────────────────────────────────────
function Hero() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden bg-brand-primary">
      {/* Background grid */}
      <div className="absolute inset-0 opacity-[0.03]"
           style={{ backgroundImage: "linear-gradient(#6d28d9 1px, transparent 1px), linear-gradient(90deg, #6d28d9 1px, transparent 1px)", backgroundSize: "64px 64px" }} />

      {/* Glow orbs */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brand-accent/15 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-brand-cyan/10 rounded-full blur-3xl pointer-events-none" />

      <div className="relative z-10 text-center max-w-5xl mx-auto px-6">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 border border-brand-accent/40 bg-brand-accent/10 rounded-full text-sm text-brand-accent mb-8">
          <span className="w-2 h-2 bg-brand-teal rounded-full animate-pulse" />
          Now in public beta — first 500 teams free
        </div>

        <h1 className="text-6xl md:text-7xl font-black text-white leading-tight mb-6">
          Your code ships itself.<br />
          <span style={{ background: "linear-gradient(135deg, #6d28d9, #06b6d4)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            Jarviis handles the rest.
          </span>
        </h1>

        <p className="text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed">
          JarviisAI autonomously crawls your app, generates test suites with Claude AI,
          executes them in parallel, deploys passing builds, and self-heals failures.
          Zero testers. Zero QA managers. Zero late nights.
        </p>

        <div className="flex items-center justify-center gap-4 flex-wrap">
          <Link href="/auth/register">
            <button className="px-8 py-4 rounded-xl text-base font-bold text-white transition-all hover:scale-105 active:scale-95"
              style={{ background: "linear-gradient(135deg, #6d28d9, #5b21b6)", boxShadow: "0 0 40px rgba(109,40,217,0.4)" }}>
              Start Free — No Credit Card
            </button>
          </Link>
          <Link href="/docs">
            <button className="px-8 py-4 rounded-xl text-base font-semibold text-slate-300 border border-slate-700 hover:border-slate-500 transition-all">
              Read the Docs →
            </button>
          </Link>
        </div>

        {/* Social proof */}
        <p className="mt-8 text-slate-500 text-sm">
          Trusted by teams shipping <strong className="text-slate-300">10,000+</strong> deployments a month
        </p>

        {/* Terminal demo */}
        <div className="mt-14 text-left bg-slate-900/80 border border-slate-700/60 rounded-2xl p-6 max-w-2xl mx-auto font-mono text-sm backdrop-blur-sm">
          <div className="flex gap-2 mb-4">
            <div className="w-3 h-3 rounded-full bg-red-500/70" />
            <div className="w-3 h-3 rounded-full bg-yellow-500/70" />
            <div className="w-3 h-3 rounded-full bg-green-500/70" />
          </div>
          <div className="space-y-2 text-slate-300">
            <p><span className="text-purple-400">$</span> <span className="text-slate-200">jarviis test https://myapp.com</span></p>
            <p className="text-slate-500">🕷️  Crawling 47 pages...</p>
            <p className="text-slate-500">🤖 Claude generating 89 tests...</p>
            <p className="text-slate-500">⚡ Executing in 4 parallel workers...</p>
            <p className="text-green-400">✓ 87/89 tests passed (97.8%) in 42s</p>
            <p className="text-slate-500">🔧 2 failures auto-healed via selector repair</p>
            <p className="text-cyan-400">🚀 Deploying to staging...</p>
            <p className="text-green-400">✅ Deployment healthy — promoting to production</p>
          </div>
        </div>
      </div>
    </section>
  );
}

// ── Features ─────────────────────────────────────────────────
const FEATURES = [
  {
    emoji: "🕷️",
    title: "AI-Powered Crawling",
    desc: "Playwright-based crawler maps every page, form, and interaction in your app. No configuration. No selectors to write.",
  },
  {
    emoji: "🤖",
    title: "Claude Generates Tests",
    desc: "Claude 3.5 Sonnet reads your app map and writes comprehensive Playwright test suites. Tests that would take your team days take seconds.",
  },
  {
    emoji: "⚡",
    title: "Parallel Execution",
    desc: "Tests run across multiple browsers simultaneously. Chrome, Firefox, WebKit — real results in under 60 seconds.",
  },
  {
    emoji: "🔧",
    title: "Self-Healing Tests",
    desc: "When selectors break from UI changes, our ML model finds the correct replacement automatically. No flaky test maintenance.",
  },
  {
    emoji: "🚀",
    title: "Zero-Downtime Deploys",
    desc: "Built-in SSH deploy engine with rolling, blue-green, and canary strategies. Test gate ensures broken code never ships.",
  },
  {
    emoji: "🛡️",
    title: "Security Scanning",
    desc: "OWASP Top 10 checks on every deploy. Security headers, CORS, injection indicators — all automated.",
  },
  {
    emoji: "🔌",
    title: "API Testing",
    desc: "Import OpenAPI 3.x or Swagger specs. Automatically test every endpoint: schema validation, auth gates, response times.",
  },
  {
    emoji: "🖥️",
    title: "Mainframe/COBOL",
    desc: "AI-powered COBOL analyzer generates test drivers, JCL stubs, and plain-English documentation for legacy systems.",
  },
];

function Features() {
  return (
    <section className="py-24 bg-slate-950 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-4xl font-black text-white mb-4">Everything your QA team does — automated</h2>
          <p className="text-slate-400 text-lg max-w-2xl mx-auto">
            One platform. Every type of testing. Zero human testers required.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {FEATURES.map((f) => (
            <div key={f.title}
                 className="bg-slate-900/60 border border-slate-700/60 rounded-2xl p-6 hover:border-purple-500/40 transition-all duration-300 group">
              <div className="text-3xl mb-4" aria-hidden>{f.emoji}</div>
              <h3 className="font-bold text-white mb-2 group-hover:text-purple-300 transition-colors">{f.title}</h3>
              <p className="text-slate-400 text-sm leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── How it works ──────────────────────────────────────────────
const STEPS = [
  { n: "01", title: "Connect your project", desc: "Add your URL or repository. No configuration files. No YAML. JarviisAI figures out the rest." },
  { n: "02", title: "AI crawls and generates", desc: "Claude maps your entire app and generates a test suite tailored to your exact UI and user flows." },
  { n: "03", title: "Tests run automatically", desc: "On every commit or on a schedule. Results in 60 seconds. Failures are explained in plain English." },
  { n: "04", title: "Passing code deploys itself", desc: "Built-in deploy engine with SSH, health checks, and one-click rollback. From PR to production without human intervention." },
];

function HowItWorks() {
  return (
    <section className="py-24 bg-slate-900 px-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-4xl font-black text-white mb-4">From zero to autonomous in 5 minutes</h2>
        </div>
        <div className="space-y-8">
          {STEPS.map((step, i) => (
            <div key={step.n} className="flex gap-6 items-start">
              <div className="flex-shrink-0 w-14 h-14 rounded-2xl bg-purple-600/20 border border-purple-500/30 flex items-center justify-center">
                <span className="font-black text-purple-400 text-lg">{step.n}</span>
              </div>
              <div className="flex-1 pt-2">
                <h3 className="text-xl font-bold text-white mb-2">{step.title}</h3>
                <p className="text-slate-400 leading-relaxed">{step.desc}</p>
              </div>
              {i < STEPS.length - 1 && (
                <div className="absolute left-7 mt-16 w-px h-8 bg-purple-500/20" style={{ position: "relative", left: -1 }} />
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── CTA ────────────────────────────────────────────────────────
function CTA() {
  return (
    <section className="py-24 bg-brand-primary px-6">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-5xl font-black text-white mb-6">
          Ship with confidence.<br />
          <span style={{ background: "linear-gradient(135deg, #6d28d9, #06b6d4)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            Every single time.
          </span>
        </h2>
        <p className="text-slate-400 text-lg mb-10">
          Join hundreds of teams who stopped writing tests manually and started shipping 3× faster.
        </p>
        <Link href="/auth/register">
          <button className="px-10 py-5 rounded-xl text-lg font-bold text-white transition-all hover:scale-105"
            style={{ background: "linear-gradient(135deg, #6d28d9, #5b21b6)", boxShadow: "0 0 60px rgba(109,40,217,0.4)" }}>
            Start Free — No Credit Card Required
          </button>
        </Link>
        <p className="mt-4 text-slate-500 text-sm">14-day free trial on Pro and Team plans.</p>
      </div>
    </section>
  );
}

// ── Nav ────────────────────────────────────────────────────────
function Nav() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-slate-950/80 backdrop-blur-md border-b border-slate-800/50">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-2xl font-black" style={{ background: "linear-gradient(135deg, #6d28d9, #06b6d4)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            JARVIIS AI
          </span>
        </Link>
        <div className="hidden md:flex items-center gap-8 text-sm text-slate-400">
          <Link href="/pricing" className="hover:text-white transition-colors">Pricing</Link>
          <Link href="/docs" className="hover:text-white transition-colors">Docs</Link>
          <Link href="/blog" className="hover:text-white transition-colors">Blog</Link>
          <Link href="/about" className="hover:text-white transition-colors">About</Link>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/auth/login">
            <button className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors">
              Sign in
            </button>
          </Link>
          <Link href="/auth/register">
            <button className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-all hover:opacity-90"
              style={{ background: "linear-gradient(135deg, #6d28d9, #5b21b6)" }}>
              Start Free
            </button>
          </Link>
        </div>
      </div>
    </nav>
  );
}

// ── Footer ─────────────────────────────────────────────────────
function Footer() {
  const links = {
    Product: [
      { label: "Features", href: "/" },
      { label: "Pricing", href: "/pricing" },
      { label: "Changelog", href: "/changelog" },
      { label: "Roadmap", href: "/roadmap" },
    ],
    Developers: [
      { label: "Documentation", href: "/docs" },
      { label: "API Reference", href: "/docs/api" },
      { label: "GitHub", href: "https://github.com/jarviisai" },
      { label: "CLI", href: "/docs/cli" },
    ],
    Company: [
      { label: "About", href: "/about" },
      { label: "Blog", href: "/blog" },
      { label: "Careers", href: "/careers" },
      { label: "Contact", href: "/contact" },
    ],
    Legal: [
      { label: "Privacy Policy", href: "/privacy" },
      { label: "Terms of Service", href: "/terms" },
      { label: "Security", href: "/security" },
      { label: "Cookie Policy", href: "/cookies" },
    ],
  };

  return (
    <footer className="bg-slate-950 border-t border-slate-800/50 py-16 px-6">
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-8 mb-12">
          <div className="col-span-2 md:col-span-1">
            <span className="text-xl font-black" style={{ background: "linear-gradient(135deg, #6d28d9, #06b6d4)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              JARVIIS AI
            </span>
            <p className="text-slate-500 text-sm mt-3 leading-relaxed">
              Autonomous testing and deployment for modern software teams.
            </p>
          </div>
          {Object.entries(links).map(([group, items]) => (
            <div key={group}>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">{group}</p>
              <ul className="space-y-3">
                {items.map(item => (
                  <li key={item.label}>
                    <Link href={item.href} className="text-slate-500 text-sm hover:text-slate-300 transition-colors">
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="border-t border-slate-800/50 pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-slate-500 text-sm">© 2026 JarviisAI. All rights reserved.</p>
          <p className="text-slate-600 text-xs">Made with Claude AI. Zero testers harmed.</p>
        </div>
      </div>
    </footer>
  );
}

// ── Page ───────────────────────────────────────────────────────
export default function HomePage() {
  return (
    <>
      <Nav />
      <main className="pt-16">
        <Hero />
        <Features />
        <HowItWorks />
        <CTA />
      </main>
      <Footer />
    </>
  );
}
