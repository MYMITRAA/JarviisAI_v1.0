"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Shield, CheckCircle2, AlertCircle, ExternalLink, RefreshCw, Copy } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore, useOrgId, useOrgSlug } from "@/store/auth";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const PROTOCOL_GUIDES = {
  saml: {
    label: "SAML 2.0",
    providers: ["Okta", "Azure AD", "Google Workspace", "OneLogin", "Ping Identity"],
    steps: [
      "Enter your IdP metadata URL (or manual config below)",
      "Download JarviisAI SP metadata",
      "Upload SP metadata to your IdP",
      "Test the connection",
    ],
  },
  oidc: {
    label: "OpenID Connect",
    providers: ["Okta", "Azure AD", "Auth0", "Google Workspace", "Keycloak"],
    steps: [
      "Enter your OIDC Discovery URL",
      "Add the Redirect URI to your OIDC application",
      "Enter Client ID and Secret",
      "Test the connection",
    ],
  },
};

export default function SSOSettingsPage() {
  const { user } = useAuthStore();
  const orgId = useOrgId();
  const orgSlug = useOrgSlug();
  const [protocol, setProtocol] = useState<"saml"|"oidc">("saml");
  const [metadataUrl, setMetadataUrl] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [discoveryUrl, setDiscoveryUrl] = useState("");
  const [enforceSSO, setEnforceSSO] = useState(false);
  const [validationResult, setValidationResult] = useState<any>(null);

  const spAcsUrl = `https://sso.jarviis.ai/api/v1/sso/saml/${orgSlug}/acs`;
  const spEntityId = `https://sso.jarviis.ai/saml/${orgSlug}`;
  const spMetadataUrl = `https://sso.jarviis.ai/api/v1/sso/saml/${orgSlug}/metadata`;
  const oidcRedirectUri = `https://sso.jarviis.ai/api/v1/sso/oidc/${orgSlug}/callback`;

  const validate = useMutation({
    mutationFn: () => apiClient.post("/sso/validate", {
      org_id: orgId,
      name: "My IdP",
      protocol,
      idp_metadata_url: protocol === "saml" ? metadataUrl : undefined,
      oidc_discovery_url: protocol === "oidc" ? discoveryUrl : undefined,
      oidc_client_id: protocol === "oidc" ? clientId : undefined,
    }),
    onSuccess: (res) => {
      setValidationResult(res.data);
      if (res.data.valid) toast.success("SSO configuration validated successfully");
      else toast.error(`Validation failed: ${res.data.error}`);
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Validation error"),
  });

  const save = useMutation({
    mutationFn: () => apiClient.post("/sso/providers", {
      org_id: orgId,
      name: "Organization SSO",
      protocol,
      idp_metadata_url: metadataUrl,
      oidc_discovery_url: discoveryUrl,
      oidc_client_id: clientId,
      oidc_client_secret: clientSecret,
      enforce_sso: enforceSSO,
    }),
    onSuccess: () => toast.success("SSO configuration saved"),
    onError: (e: any) => toast.error(e?.response?.data?.detail || "Save failed"),
  });

  const copy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`Copied ${label}`);
  };

  const guide = PROTOCOL_GUIDES[protocol];

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-black text-content-primary flex items-center gap-3">
          <Shield className="w-6 h-6 text-brand-accent" />
          Enterprise SSO
        </h1>
        <p className="text-content-muted text-sm mt-1">
          Configure SAML 2.0 or OpenID Connect for your organization
        </p>
      </div>

      {/* Protocol selector */}
      <div className="glass-card p-5">
        <h2 className="font-semibold text-content-primary mb-3">Protocol</h2>
        <div className="flex gap-3">
          {(["saml","oidc"] as const).map(p => (
            <button key={p} onClick={() => setProtocol(p)}
              className={cn(
                "flex-1 py-3 rounded-xl border text-sm font-semibold transition-all",
                protocol === p
                  ? "border-brand-accent bg-brand-accent/10 text-brand-accent"
                  : "border-surface-border text-content-muted hover:border-surface-muted"
              )}>
              {PROTOCOL_GUIDES[p].label}
            </button>
          ))}
        </div>
        <p className="text-xs text-content-muted mt-3">
          Supports: {guide.providers.join(", ")}
        </p>
      </div>

      {/* SP values for IdP config */}
      <div className="glass-card p-5">
        <h2 className="font-semibold text-content-primary mb-3">
          {protocol === "saml" ? "Add these to your IdP" : "OIDC Redirect URI"}
        </h2>
        <div className="space-y-3">
          {protocol === "saml" ? (
            <>
              {[
                { label: "ACS URL", value: spAcsUrl },
                { label: "Entity ID / Audience", value: spEntityId },
                { label: "SP Metadata URL", value: spMetadataUrl },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center gap-2 p-2.5 bg-surface-overlay rounded-lg border border-surface-border">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-content-muted">{label}</p>
                    <p className="text-xs font-mono text-content-primary truncate">{value}</p>
                  </div>
                  <button onClick={() => copy(value, label)} className="text-brand-accent hover:text-brand-cyan transition-colors flex-shrink-0">
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
              <a href={spMetadataUrl} target="_blank" rel="noopener noreferrer"
                 className="flex items-center gap-1.5 text-xs text-brand-accent hover:underline">
                <ExternalLink className="w-3 h-3" />
                Download SP Metadata XML
              </a>
            </>
          ) : (
            <div className="flex items-center gap-2 p-2.5 bg-surface-overlay rounded-lg border border-surface-border">
              <div className="flex-1 min-w-0">
                <p className="text-xs text-content-muted">Redirect URI</p>
                <p className="text-xs font-mono text-content-primary truncate">{oidcRedirectUri}</p>
              </div>
              <button onClick={() => copy(oidcRedirectUri, "Redirect URI")} className="text-brand-accent hover:text-brand-cyan transition-colors">
                <Copy className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* IdP configuration */}
      <div className="glass-card p-5 space-y-4">
        <h2 className="font-semibold text-content-primary">IdP Configuration</h2>

        {protocol === "saml" ? (
          <div>
            <label className="block text-sm font-medium text-content-secondary mb-1.5">
              IdP Metadata URL <span className="text-xs text-content-muted">(recommended)</span>
            </label>
            <input value={metadataUrl} onChange={e => setMetadataUrl(e.target.value)}
              placeholder="https://your-idp.com/app/metadata"
              className="input-field font-mono text-sm" />
            <p className="text-xs text-content-muted mt-1">
              Okta: Apps → Sign On → SAML Signing Certificates → "Identity Provider metadata"
            </p>
          </div>
        ) : (
          <>
            <div>
              <label className="block text-sm font-medium text-content-secondary mb-1.5">Discovery URL</label>
              <input value={discoveryUrl} onChange={e => setDiscoveryUrl(e.target.value)}
                placeholder="https://your-idp.com/.well-known/openid-configuration"
                className="input-field font-mono text-sm" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-content-secondary mb-1.5">Client ID</label>
                <input value={clientId} onChange={e => setClientId(e.target.value)}
                  placeholder="0oa..." className="input-field font-mono text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-content-secondary mb-1.5">Client Secret</label>
                <input value={clientSecret} onChange={e => setClientSecret(e.target.value)}
                  type="password" placeholder="••••••••" className="input-field text-sm" />
              </div>
            </div>
          </>
        )}

        {/* Enforce SSO */}
        <div className="flex items-center justify-between py-2 border-t border-surface-border">
          <div>
            <p className="text-sm font-medium text-content-primary">Enforce SSO</p>
            <p className="text-xs text-content-muted">Disable password login — all users must authenticate via SSO</p>
          </div>
          <label className="flex items-center cursor-pointer">
            <input type="checkbox" checked={enforceSSO} onChange={e => setEnforceSSO(e.target.checked)}
              className="w-4 h-4 accent-brand-accent" />
          </label>
        </div>

        {/* Validation result */}
        <AnimatePresence>
          {validationResult && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
              className={cn("rounded-lg p-3 border text-sm",
                validationResult.valid
                  ? "bg-brand-teal/5 border-brand-teal/20 text-brand-teal"
                  : "bg-brand-crimson/5 border-brand-crimson/20 text-brand-crimson"
              )}>
              <div className="flex items-center gap-2">
                {validationResult.valid ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                <span>{validationResult.valid ? "Configuration is valid" : validationResult.error}</span>
              </div>
              {validationResult.issuer && (
                <p className="text-xs mt-1 text-content-muted">Issuer: {validationResult.issuer}</p>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex gap-3">
          <button onClick={() => validate.mutate()} disabled={validate.isPending}
            className="btn-secondary flex items-center gap-2 text-sm">
            {validate.isPending ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" />Testing...</> : "Test Connection"}
          </button>
          <button onClick={() => save.mutate()} disabled={save.isPending}
            className="btn-primary flex items-center gap-2 text-sm">
            {save.isPending ? "Saving..." : "Save Configuration"}
          </button>
        </div>
      </div>
    </div>
  );
}
