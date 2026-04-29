"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Github, Mail, Lock, User, Eye, EyeOff, Zap, CheckCircle2, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TerminalText } from "@/components/ui/TerminalText";
import { CodeRainBackground } from "@/components/ui/CodeRainBackground";
import { cn, slugify } from "@/lib/utils";

// ── Schemas ───────────────────────────────────────────────────
const step1Schema = z.object({
  full_name: z.string().min(2, "Name must be at least 2 characters"),
  email: z.string().email("Enter a valid email"),
  password: z
    .string()
    .min(10, "Minimum 10 characters")
    .regex(/[A-Z]/, "Must contain uppercase letter")
    .regex(/[a-z]/, "Must contain lowercase letter")
    .regex(/\d/, "Must contain a number")
    .regex(/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/, "Must contain a special character")
    .regex(/[A-Z]/, "At least one uppercase letter")
    .regex(/[a-z]/, "At least one lowercase letter")
    .regex(/\d/, "At least one number"),
  confirm_password: z.string(),
}).refine((d) => d.password === d.confirm_password, {
  message: "Passwords don't match",
  path: ["confirm_password"],
});

const step2Schema = z.object({
  org_name: z.string().min(2, "Organization name must be at least 2 characters"),
  org_slug: z
    .string()
    .min(3, "Slug must be at least 3 characters")
    .max(50, "Slug must be under 50 characters")
    .regex(/^[a-z0-9-]+$/, "Only lowercase letters, numbers, and hyphens"),
  use_case: z.enum(["solo", "team", "enterprise"]).optional(),
});

type Step1Form = z.infer<typeof step1Schema>;
type Step2Form = z.infer<typeof step2Schema>;

// ── Password strength indicator ────────────────────────────────
function PasswordStrength({ password }: { password: string }) {
  const checks = [
    { label: "10+ characters", ok: password.length >= 10 },
    { label: "Special char (!@#...)", ok: /[!@#$%^&*()_+\-=]/.test(password) },
    { label: "Uppercase", ok: /[A-Z]/.test(password) },
    { label: "Lowercase", ok: /[a-z]/.test(password) },
    { label: "Number", ok: /\d/.test(password) },
  ];
  const score = checks.filter((c) => c.ok).length;
  const colors = ["bg-brand-crimson", "bg-brand-crimson", "bg-yellow-500", "bg-yellow-400", "bg-brand-teal"];

  return (
    <div className="mt-2 space-y-2">
      <div className="flex gap-1">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className={cn(
              "h-1 flex-1 rounded-full transition-all duration-300",
              i < score ? colors[score] : "bg-surface-border"
            )}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {checks.map((c) => (
          <span key={c.label} className={cn("text-xs flex items-center gap-1", c.ok ? "text-brand-teal" : "text-content-muted")}>
            <CheckCircle2 className="w-3 h-3" />
            {c.label}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────
export default function RegisterPage() {
  const router = useRouter();
  const { setTokens, setUser } = useAuthStore();
  const searchParams = useSearchParams();
  // GitHub OAuth redirects to ?step=2 for new users to complete org setup
  const initialStep = searchParams.get("step") === "2" ? 2 : 1;
  const [step, setStep] = useState(initialStep);
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [step1Data, setStep1Data] = useState<Step1Form | null>(null);
  const [accessTokenTemp, setAccessTokenTemp] = useState<string | null>(null);

  const form1 = useForm<Step1Form>({ resolver: zodResolver(step1Schema) });
  const form2 = useForm<Step2Form>({ resolver: zodResolver(step2Schema) });

  const watchedPassword = form1.watch("password", "");
  const watchedOrgName = form2.watch("org_name", "");

  // Auto-generate slug from org name
  const handleOrgNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    form2.setValue("org_name", e.target.value);
    const slug = slugify(e.target.value);
    form2.setValue("org_slug", slug, { shouldValidate: true });
  };

  // Step 1 — Create account
  const onStep1Submit = async (data: Step1Form) => {
    setIsLoading(true);
    try {
      await authApi.register({ email: data.email, password: data.password, full_name: data.full_name });
      // Log in immediately
      const tokens = await authApi.login({ email: data.email, password: data.password });
      setAccessTokenTemp(tokens.access_token);
      setTokens(tokens.access_token, tokens.refresh_token);
      setStep1Data(data);
      setStep(2);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Registration failed. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  // Step 2 — Create org
  const onStep2Submit = async (data: Step2Form) => {
    setIsLoading(true);
    try {
      const result = await authApi.completeOnboarding({
        org_name: data.org_name,
        org_slug: data.org_slug,
        use_case: data.use_case,
      });
      setTokens(result.access_token, result.refresh_token);
      setUser(result.user);
      toast.success("Instance initialized. Welcome to JarviisAI! 🚀");
      router.push("/dashboard");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Setup failed. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleGithubLogin = () => {
    window.location.href = `${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/github`;
  };

  const useCaseOptions = [
    { value: "solo", label: "Solo Dev", desc: "Just me, shipping fast" },
    { value: "team", label: "Team", desc: "Building together" },
    { value: "enterprise", label: "Enterprise", desc: "Large-scale deployment" },
  ];

  return (
    <div className="relative min-h-screen flex items-center justify-center overflow-hidden bg-brand-primary">
      <CodeRainBackground />
      <div className="absolute top-1/3 right-1/4 w-80 h-80 bg-brand-accent/8 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/3 left-1/4 w-80 h-80 bg-brand-cyan/8 rounded-full blur-3xl pointer-events-none" />

      <div className="relative z-10 w-full max-w-md mx-4">
        {/* Step indicators */}
        <div className="flex items-center justify-center gap-3 mb-6">
          {[1, 2].map((s) => (
            <div key={s} className="flex items-center gap-2">
              <div className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all duration-300",
                s < step ? "bg-brand-teal text-white" :
                s === step ? "bg-brand-accent text-white shadow-glow-accent" :
                "bg-surface-border text-content-muted"
              )}>
                {s < step ? <CheckCircle2 className="w-4 h-4" /> : s}
              </div>
              {s < 2 && (
                <div className={cn("w-12 h-px transition-all duration-500", s < step ? "bg-brand-teal" : "bg-surface-border")} />
              )}
            </div>
          ))}
        </div>

        <div className="glass-card p-8">
          {/* Header */}
          <div className="text-center mb-7">
            <div className="flex items-center justify-center gap-2 mb-3">
              <Zap className="w-7 h-7 text-brand-accent" />
              <span className="text-xl font-black text-gradient">JARVIIS AI</span>
            </div>
            <TerminalText
              text={step === 1 ? "jarviis init --new-instance" : "jarviis init --org setup"}
              className="text-brand-neon font-mono text-sm mb-3"
            />
            <h1 className="text-2xl font-bold text-content-primary">
              {step === 1 ? "Initialize Your Instance" : "Configure Your Workspace"}
            </h1>
            <p className="text-content-muted text-sm mt-1">
              {step === 1 ? "Step 1 of 2 — Create your account" : "Step 2 of 2 — Set up your organization"}
            </p>
          </div>

          <AnimatePresence mode="wait">
            {/* ── Step 1 ─────────────────────────────────────── */}
            {step === 1 && (
              <motion.div
                key="step1"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.25 }}
              >
                {/* GitHub */}
                <motion.button
                  whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                  onClick={handleGithubLogin}
                  className="w-full flex items-center justify-center gap-3 px-4 py-3
                             bg-surface-overlay border border-surface-border rounded-lg
                             text-content-primary font-medium text-sm
                             hover:border-brand-accent hover:shadow-glow-accent
                             transition-all duration-200 mb-4"
                >
                  <Github className="w-5 h-5" />
                  Initialize with GitHub
                </motion.button>

                <div className="flex items-center gap-3 mb-5">
                  <div className="flex-1 h-px bg-surface-border" />
                  <span className="text-content-muted text-xs font-mono">or use email</span>
                  <div className="flex-1 h-px bg-surface-border" />
                </div>

                <form onSubmit={form1.handleSubmit(onStep1Submit)} className="space-y-4">
                  {/* Full name */}
                  <div>
                    <label className="block text-sm font-medium text-content-secondary mb-1.5">Full Name</label>
                    <div className="relative">
                      <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-content-muted" />
                      <input
                        {...form1.register("full_name")}
                        placeholder="Ada Lovelace"
                        autoComplete="name"
                        className="input-field pl-10"
                      />
                    </div>
                    {form1.formState.errors.full_name && (
                      <p className="text-brand-crimson text-xs mt-1">{form1.formState.errors.full_name.message}</p>
                    )}
                  </div>

                  {/* Email */}
                  <div>
                    <label className="block text-sm font-medium text-content-secondary mb-1.5">Email</label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-content-muted" />
                      <input
                        {...form1.register("email")}
                        type="email"
                        placeholder="ada@company.com"
                        autoComplete="email"
                        className="input-field pl-10"
                      />
                    </div>
                    {form1.formState.errors.email && (
                      <p className="text-brand-crimson text-xs mt-1">{form1.formState.errors.email.message}</p>
                    )}
                  </div>

                  {/* Password */}
                  <div>
                    <label className="block text-sm font-medium text-content-secondary mb-1.5">Password</label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-content-muted" />
                      <input
                        {...form1.register("password")}
                        type={showPassword ? "text" : "password"}
                        placeholder="Minimum 8 characters"
                        autoComplete="new-password"
                        className="input-field pl-10 pr-10"
                      />
                      <button type="button" onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-content-muted hover:text-content-primary">
                        {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                    {watchedPassword && <PasswordStrength password={watchedPassword} />}
                    {form1.formState.errors.password && (
                      <p className="text-brand-crimson text-xs mt-1">{form1.formState.errors.password.message}</p>
                    )}
                  </div>

                  {/* Confirm password */}
                  <div>
                    <label className="block text-sm font-medium text-content-secondary mb-1.5">Confirm Password</label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-content-muted" />
                      <input
                        {...form1.register("confirm_password")}
                        type="password"
                        placeholder="Re-enter password"
                        autoComplete="new-password"
                        className="input-field pl-10"
                      />
                    </div>
                    {form1.formState.errors.confirm_password && (
                      <p className="text-brand-crimson text-xs mt-1">{form1.formState.errors.confirm_password.message}</p>
                    )}
                  </div>

                  <motion.button
                    whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
                    type="submit" disabled={isLoading}
                    className="btn-primary w-full mt-2"
                  >
                    {isLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Initializing...
                      </span>
                    ) : (
                      <span className="flex items-center justify-center gap-2">
                        Continue <ArrowRight className="w-4 h-4" />
                      </span>
                    )}
                  </motion.button>
                </form>

                <p className="text-center text-content-muted text-sm mt-5">
                  Already have an instance?{" "}
                  <Link href="/auth/login" className="text-brand-accent hover:text-brand-cyan transition-colors font-medium">
                    Resume session →
                  </Link>
                </p>
              </motion.div>
            )}

            {/* ── Step 2 ─────────────────────────────────────── */}
            {step === 2 && (
              <motion.div
                key="step2"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.25 }}
              >
                <form onSubmit={form2.handleSubmit(onStep2Submit)} className="space-y-5">
                  {/* Org name */}
                  <div>
                    <label className="block text-sm font-medium text-content-secondary mb-1.5">
                      Organization Name
                    </label>
                    <input
                      {...form2.register("org_name")}
                      onChange={handleOrgNameChange}
                      placeholder="Acme Corp"
                      className="input-field"
                    />
                    {form2.formState.errors.org_name && (
                      <p className="text-brand-crimson text-xs mt-1">{form2.formState.errors.org_name.message}</p>
                    )}
                  </div>

                  {/* Org slug */}
                  <div>
                    <label className="block text-sm font-medium text-content-secondary mb-1.5">
                      Workspace URL
                    </label>
                    <div className="flex items-center gap-0">
                      <span className="px-3 py-3 bg-surface-border text-content-muted text-sm rounded-l-lg border border-r-0 border-surface-border font-mono">
                        jarviis.ai/
                      </span>
                      <input
                        {...form2.register("org_slug")}
                        placeholder="acme-corp"
                        className="input-field rounded-l-none font-mono"
                      />
                    </div>
                    {form2.formState.errors.org_slug && (
                      <p className="text-brand-crimson text-xs mt-1">{form2.formState.errors.org_slug.message}</p>
                    )}
                  </div>

                  {/* Use case */}
                  <div>
                    <label className="block text-sm font-medium text-content-secondary mb-2">
                      How are you planning to use JarviisAI?
                    </label>
                    <div className="grid grid-cols-3 gap-2">
                      {useCaseOptions.map((opt) => {
                        const selected = form2.watch("use_case") === opt.value;
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            onClick={() => form2.setValue("use_case", opt.value as any)}
                            className={cn(
                              "p-3 rounded-lg border text-left transition-all duration-200",
                              selected
                                ? "border-brand-accent bg-brand-accent/10 shadow-glow-accent"
                                : "border-surface-border hover:border-surface-muted"
                            )}
                          >
                            <div className="text-sm font-semibold text-content-primary">{opt.label}</div>
                            <div className="text-xs text-content-muted mt-0.5">{opt.desc}</div>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <motion.button
                    whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
                    type="submit" disabled={isLoading}
                    className="btn-primary w-full"
                  >
                    {isLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Launching workspace...
                      </span>
                    ) : (
                      <span className="flex items-center justify-center gap-2">
                        Launch Workspace 🚀
                      </span>
                    )}
                  </motion.button>

                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="w-full text-center text-content-muted text-sm hover:text-content-secondary transition-colors"
                  >
                    ← Back to account setup
                  </button>
                </form>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <p className="text-center text-content-muted text-xs mt-4">
          By continuing, you agree to JarviisAI's{" "}
          <a href="#" className="text-brand-accent hover:underline">Terms of Service</a>
          {" "}and{" "}
          <a href="#" className="text-brand-accent hover:underline">Privacy Policy</a>.
        </p>
      </div>
    </div>
  );
}
