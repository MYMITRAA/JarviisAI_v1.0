"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";
import Link from "next/link";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to error tracking (Sentry etc.)
    console.error("Global error:", error);
  }, [error]);

  return (
    <html>
      <body className="min-h-screen bg-brand-primary flex items-center justify-center p-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="max-w-md w-full text-center"
        >
          <div className="w-16 h-16 bg-brand-crimson/10 border border-brand-crimson/30 rounded-2xl flex items-center justify-center mx-auto mb-6">
            <AlertTriangle className="w-8 h-8 text-brand-crimson" />
          </div>
          <h1 className="text-2xl font-black text-content-primary mb-2">Something went wrong</h1>
          <p className="text-content-muted text-sm mb-6">
            An unexpected error occurred. Our team has been notified.
          </p>
          {error.digest && (
            <p className="text-xs text-content-muted font-mono mb-4">Error ID: {error.digest}</p>
          )}
          <div className="flex items-center justify-center gap-3">
            <motion.button
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
              onClick={reset}
              className="flex items-center gap-2 px-4 py-2 bg-brand-accent text-white rounded-lg text-sm font-semibold"
            >
              <RefreshCw className="w-4 h-4" /> Try Again
            </motion.button>
            <Link href="/dashboard">
              <button className="flex items-center gap-2 px-4 py-2 border border-surface-border text-content-muted rounded-lg text-sm hover:border-surface-muted transition-all">
                <Home className="w-4 h-4" /> Dashboard
              </button>
            </Link>
          </div>
        </motion.div>
      </body>
    </html>
  );
}
