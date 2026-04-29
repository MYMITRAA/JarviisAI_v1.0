"use client";

import { motion } from "framer-motion";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center justify-center min-h-96"
    >
      <div className="text-center max-w-sm">
        <div className="w-12 h-12 bg-brand-crimson/10 border border-brand-crimson/30 rounded-xl flex items-center justify-center mx-auto mb-4">
          <AlertTriangle className="w-6 h-6 text-brand-crimson" />
        </div>
        <h2 className="font-semibold text-content-primary mb-2">Page failed to load</h2>
        <p className="text-content-muted text-sm mb-4">
          {error.message || "An unexpected error occurred on this page."}
        </p>
        <motion.button
          whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          onClick={reset}
          className="flex items-center gap-2 px-4 py-2 bg-brand-accent/15 text-brand-accent border border-brand-accent/30 rounded-lg text-sm font-medium mx-auto"
        >
          <RefreshCw className="w-4 h-4" /> Reload page
        </motion.button>
      </div>
    </motion.div>
  );
}
