"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { Zap } from "lucide-react";

export default function HomePage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();

  useEffect(() => {
    if (isAuthenticated) {
      router.replace("/dashboard");
    } else {
      router.replace("/auth/login");
    }
  }, [isAuthenticated]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-primary">
      <div className="flex flex-col items-center gap-3">
        <Zap className="w-12 h-12 text-brand-accent animate-pulse" />
        <p className="text-content-muted text-sm font-mono">Initializing...</p>
      </div>
    </div>
  );
}
