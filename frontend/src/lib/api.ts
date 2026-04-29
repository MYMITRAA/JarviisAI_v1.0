import axios, { AxiosInstance, InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/store/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Axios instance ─────────────────────────────────────────────
export const apiClient: AxiosInstance = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

// ── Request interceptor — inject access token ──────────────────
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor — auto refresh on 401 ────────────────
let isRefreshing = false;
let failedQueue: Array<{ resolve: Function; reject: Function }> = [];

const processQueue = (error: any, token: string | null) => {
  failedQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token)));
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;

    if (error.response?.status === 401 && !original._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          original.headers.Authorization = `Bearer ${token}`;
          return apiClient(original);
        });
      }

      original._retry = true;
      isRefreshing = true;

      const refreshToken = useAuthStore.getState().refreshToken;
      if (!refreshToken) {
        useAuthStore.getState().logout();
        window.location.href = "/auth/login";
        return Promise.reject(error);
      }

      try {
        const { data } = await axios.post(`${API_URL}/api/v1/auth/refresh`, {
          refresh_token: refreshToken,
        });

        const { access_token, refresh_token } = data;
        useAuthStore.getState().setTokens(access_token, refresh_token);
        apiClient.defaults.headers.common.Authorization = `Bearer ${access_token}`;
        processQueue(null, access_token);
        original.headers.Authorization = `Bearer ${access_token}`;
        return apiClient(original);
      } catch (refreshError) {
        processQueue(refreshError, null);
        useAuthStore.getState().logout();
        window.location.href = "/auth/login";
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// ── Auth API ──────────────────────────────────────────────────
export const authApi = {
  register: (data: { email: string; password: string; full_name?: string }) =>
    apiClient.post("/auth/register", data).then((r) => r.data),

  login: (data: { email: string; password: string }) =>
    apiClient.post("/auth/login", data).then((r) => r.data),

  logout: (refresh_token: string) =>
    apiClient.post("/auth/logout", { refresh_token }).then((r) => r.data),

  getMe: () => apiClient.get("/users/me").then((r) => r.data),

  updateMe: (data: { full_name?: string; avatar_url?: string }) =>
    apiClient.patch("/users/me", data).then((r) => r.data),

  verifyEmail: (token: string) =>
    apiClient.post("/auth/verify-email", { token }).then((r) => r.data),

  requestPasswordReset: (email: string) =>
    apiClient.post("/auth/password-reset/request", { email }).then((r) => r.data),

  confirmPasswordReset: (token: string, new_password: string) =>
    apiClient.post("/auth/password-reset/confirm", { token, new_password }).then((r) => r.data),

  completeOnboarding: (data: { org_name: string; org_slug: string; use_case?: string }) =>
    apiClient.post("/auth/onboarding/complete", data).then((r) => r.data),
};

// ── Organizations API ─────────────────────────────────────────
export const orgApi = {
  create: (data: { name: string; slug: string; description?: string }) =>
    apiClient.post("/organizations", data).then((r) => r.data),

  get: (slug: string) =>
    apiClient.get(`/organizations/${slug}`).then((r) => r.data),

  update: (orgId: string, data: { name?: string; description?: string; logo_url?: string }) =>
    apiClient.patch(`/organizations/${orgId}`, data).then((r) => r.data),

  getMembers: (orgId: string) =>
    apiClient.get(`/organizations/${orgId}/members`).then((r) => r.data),

  inviteMember: (orgId: string, data: { email: string; role: string }) =>
    apiClient.post(`/organizations/${orgId}/invites`, data).then((r) => r.data),

  acceptInvite: (token: string) =>
    apiClient.post(`/organizations/invites/${token}/accept`).then((r) => r.data),
};
