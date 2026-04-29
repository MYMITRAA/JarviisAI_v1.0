import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import Cookies from "js-cookie";

interface User {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  is_email_verified: boolean;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  // Org context — included in JWT payload and /users/me response
  org_id: string;
  org_slug: string;
  org_name?: string;
  role: "owner" | "admin" | "member";
  plan: "free" | "pro" | "team" | "enterprise";
  // Trial
  trial_active: boolean;
  trial_hours_remaining: number;
  // Admin
  is_superadmin?: boolean;
  // SSO
  sso_provider?: string | null;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  isAuthenticated: boolean;

  setTokens: (access: string, refresh: string) => void;
  setUser: (user: User) => void;
  logout: () => void;
  updateUser: (updates: Partial<User>) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,

      setTokens: (access, refresh) => {
        Cookies.set("jarviis_refresh", refresh, {
          expires: 7,
          sameSite: "strict",
          secure: process.env.NODE_ENV === "production",
        });
        set({ accessToken: access, refreshToken: refresh, isAuthenticated: true });
      },

      setUser: (user) => set({ user }),

      logout: () => {
        Cookies.remove("jarviis_refresh");
        set({ accessToken: null, refreshToken: null, user: null, isAuthenticated: false });
      },

      updateUser: (updates) =>
        set((state) => ({
          user: state.user ? { ...state.user, ...updates } : null,
        })),
    }),
    {
      name: "jarviis-auth",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);

// ── Typed selector helpers ────────────────────────────────────
// Use these instead of (user as any)?.org_id throughout the app
export const useOrgId = () => useAuthStore((s) => s.user?.org_id ?? "");
export const useOrgSlug = () => useAuthStore((s) => s.user?.org_slug ?? "");
export const usePlan = () => useAuthStore((s) => s.user?.plan ?? "free");
export const useRole = () => useAuthStore((s) => s.user?.role ?? "member");

export const useTrialActive = () => useAuthStore((s) => s.user?.trial_active ?? false);
export const useTrialHours = () => useAuthStore((s) => s.user?.trial_hours_remaining ?? 0);
