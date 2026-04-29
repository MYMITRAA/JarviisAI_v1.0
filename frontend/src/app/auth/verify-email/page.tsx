"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { CheckCircle2, XCircle, Mail, Loader2 } from "lucide-react";
import { authApi } from "@/lib/api";
import Link from "next/link";

export default function VerifyEmailPage() {
  const params = useSearchParams();
  const router = useRouter();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const token = params.get("token");
    if (!token) {
      setStatus("error");
      setMessage("Missing verification token. Please use the link from your email.");
      return;
    }

    authApi.verifyEmail(token)
      .then(() => {
        setStatus("success");
        setMessage("Your email has been verified. You can now log in.");
      })
      .catch((err) => {
        setStatus("error");
        setMessage(err?.response?.data?.detail || "Invalid or expired verification link.");
      });
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-primary">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card p-10 text-center max-w-sm w-full mx-4"
      >
        <div className="flex justify-center mb-5">
          {status === "loading" && <Loader2 className="w-12 h-12 text-brand-accent animate-spin" />}
          {status === "success" && <CheckCircle2 className="w-12 h-12 text-brand-teal" />}
          {status === "error" && <XCircle className="w-12 h-12 text-brand-crimson" />}
        </div>
        <h1 className="text-xl font-bold text-content-primary mb-2">
          {status === "loading" ? "Verifying..." : status === "success" ? "Email Verified!" : "Verification Failed"}
        </h1>
        <p className="text-content-muted text-sm mb-6">{message}</p>
        {status !== "loading" && (
          <Link href="/auth/login" className="btn-primary inline-block">
            Resume Session →
          </Link>
        )}
      </motion.div>
    </div>
  );
}
