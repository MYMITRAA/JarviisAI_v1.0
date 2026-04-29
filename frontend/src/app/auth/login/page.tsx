"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Github, Mail, Lock, Eye, EyeOff, Zap } from "lucide-react";
import { toast } from "sonner";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { TerminalText } from "@/components/ui/TerminalText";
import { CodeRainBackground } from "@/components/ui/CodeRainBackground";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});
type LoginForm = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const { setTokens, setUser } = useAuthStore();
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginForm) => {
    setIsLoading(true);
    try {
      const res = await authApi.login(data);
      setTokens(res.access_token, res.refresh_token);
      const user = await authApi.getMe();
      setUser(user);
      toast.success("Session resumed. Welcome back.");
      router.push("/dashboard");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Invalid credentials");
    } finally {
      setIsLoading(false);
    }
  };

  const handleGithubLogin = () => {
    window.location.href = `${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/github`;
  };

  return (
    <div className="relative min-h-screen flex items-center justify-center overflow-hidden bg-brand-primary">
      {/* Animated background */}
      <CodeRainBackground />

      {/* Glow orbs */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brand-accent/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-brand-cyan/10 rounded-full blur-3xl pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="relative z-10 w-full max-w-md mx-4"
      >
        {/* Card */}
        <div className="glass-card p-8">
          {/* Header */}
          <div className="text-center mb-8">
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.1 }}
              className="flex items-center justify-center gap-2 mb-4"
            >
              <Zap className="w-8 h-8 text-brand-accent" />
              <span className="text-2xl font-black text-gradient">JARVIIS AI</span>
            </motion.div>

            <TerminalText
              text="resume_session --user [you@email.com]"
              className="text-brand-neon font-mono text-sm mb-4"
            />

            <h1 className="text-2xl font-bold text-content-primary">Resume Session</h1>
            <p className="text-content-muted text-sm mt-1">
              Your tests are waiting.
            </p>
          </div>

          {/* GitHub OAuth */}
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleGithubLogin}
            className="w-full flex items-center justify-center gap-3 px-4 py-3 
                       bg-surface-overlay border border-surface-border rounded-lg
                       text-content-primary font-medium text-sm
                       hover:border-brand-accent hover:shadow-glow-accent
                       transition-all duration-200 mb-4"
          >
            <Github className="w-5 h-5" />
            Continue with GitHub
          </motion.button>

          {/* Divider */}
          <div className="flex items-center gap-3 mb-6">
            <div className="flex-1 h-px bg-surface-border" />
            <span className="text-content-muted text-xs font-mono">or authenticate with</span>
            <div className="flex-1 h-px bg-surface-border" />
          </div>

          {/* Email/password form */}
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-content-secondary mb-1.5">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-content-muted" />
                <input
                  {...register("email")}
                  type="email"
                  placeholder="you@company.com"
                  autoComplete="email"
                  className="input-field pl-10"
                />
              </div>
              {errors.email && (
                <p className="text-brand-crimson text-xs mt-1">{errors.email.message}</p>
              )}
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-sm font-medium text-content-secondary">
                  Password
                </label>
                <Link
                  href="/auth/reset-password"
                  className="text-xs text-brand-accent hover:text-brand-cyan transition-colors"
                >
                  Reset credentials
                </Link>
              </div>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-content-muted" />
                <input
                  {...register("password")}
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••••••"
                  autoComplete="current-password"
                  className="input-field pl-10 pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-content-muted hover:text-content-primary"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {errors.password && (
                <p className="text-brand-crimson text-xs mt-1">{errors.password.message}</p>
              )}
            </div>

            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              type="submit"
              disabled={isLoading}
              className="btn-primary w-full mt-6"
            >
              {isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Authenticating...
                </span>
              ) : (
                "Resume Session →"
              )}
            </motion.button>
          </form>

          {/* Footer */}
          <p className="text-center text-content-muted text-sm mt-6">
            No instance?{" "}
            <Link href="/auth/register" className="text-brand-accent hover:text-brand-cyan transition-colors font-medium">
              Initialize one →
            </Link>
          </p>
        </div>

        {/* Bottom text */}
        <p className="text-center text-content-muted text-xs mt-4">
          By continuing, you agree to JarviisAI's Terms of Service and Privacy Policy.
        </p>
      </motion.div>
    </div>
  );
}
