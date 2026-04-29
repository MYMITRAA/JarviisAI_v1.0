"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { Zap, CheckCircle2, AlertCircle } from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { authApi } from "@/lib/api";

export default function AuthCallbackPage() {
  const router = useRouter();
  const params = useSearchParams();
  const { setTokens, setUser } = useAuthStore();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("Authenticating with GitHub...");

  useEffect(() => {
    const handle = async () => {
      const access_token = params.get("access_token");
      const refresh_token = params.get("refresh_token");
      const is_new = params.get("is_new") === "true";
      const error = params.get("error");

      if (error) {
        setStatus("error");
        setMessage("GitHub authentication failed. Please try again.");
        setTimeout(() => router.push("/auth/login"), 3000);
        return;
      }

      if (!access_token || !refresh_token) {
        setStatus("error");
        setMessage("Invalid callback — missing tokens.");
        setTimeout(() => router.push("/auth/login"), 3000);
        return;
      }

      setTokens(access_token, refresh_token);
      setMessage("Fetching your profile...");

      try {
        const user = await authApi.getMe();
        setUser(user);
        setStatus("success");

        if (is_new) {
          setMessage("Account created! Setting up your workspace...");
          setTimeout(() => router.push("/auth/register?step=2"), 1200);
        } else {
          setMessage("Welcome back! Redirecting to your dashboard...");
          setTimeout(() => router.push("/dashboard"), 1200);
        }
      } catch {
        setStatus("error");
        setMessage("Could not fetch user profile. Please try again.");
        setTimeout(() => router.push("/auth/login"), 3000);
      }
    };

    handle();
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-primary">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-card p-10 text-center max-w-sm w-full mx-4"
      >
        <div className="flex justify-center mb-5">
          {status === "loading" && (
            <div className="relative">
              <Zap className="w-12 h-12 text-brand-accent animate-pulse" />
              <div className="absolute inset-0 rounded-full border-2 border-brand-accent/30 animate-ping" />
            </div>
          )}
          {status === "success" && (
            <CheckCircle2 className="w-12 h-12 text-brand-teal" />
          )}
          {status === "error" && (
            <AlertCircle className="w-12 h-12 text-brand-crimson" />
          )}
        </div>

        <h2 className="text-xl font-bold text-content-primary mb-2">
          {status === "loading" && "Initializing..."}
          {status === "success" && "Authenticated!"}
          {status === "error" && "Authentication Failed"}
        </h2>
        <p className="text-content-muted text-sm">{message}</p>

        {status === "loading" && (
          <div className="mt-5 flex justify-center gap-1">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className="w-2 h-2 bg-brand-accent rounded-full"
                animate={{ scale: [1, 1.5, 1], opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
              />
            ))}
          </div>
        )}
      </motion.div>
    </div>
  );
}
