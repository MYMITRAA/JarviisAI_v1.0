/**
 * Feature flags client — evaluates all flags from jarviis-flags service on load.
 * 
 * Usage:
 *   const flags = useFeatureFlags();
 *   if (flags.cobol_testing) { ... }
 */

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useOrgId, usePlan } from "@/store/auth";

export interface FeatureFlags {
  cobol_testing:         boolean;
  mobile_testing:        boolean;
  visual_regression:     boolean;
  api_testing:           boolean;
  jarviis_ai_assistant:  boolean;
  enterprise_sso:        boolean;
  scim_provisioning:     boolean;
  ai_test_healing:       boolean;
  advanced_analytics:    boolean;
  compliance_exports:    boolean;
  maintenance_mode:      boolean;
  new_dashboard_v2:      boolean;
  [key: string]: boolean;
}

const DEFAULT_FLAGS: FeatureFlags = {
  cobol_testing:         true,
  mobile_testing:        true,
  visual_regression:     true,
  api_testing:           true,
  jarviis_ai_assistant:  true,
  enterprise_sso:        true,
  scim_provisioning:     false,
  ai_test_healing:       true,
  advanced_analytics:    true,
  compliance_exports:    true,
  maintenance_mode:      false,
  new_dashboard_v2:      false,
};

export function useFeatureFlags(): FeatureFlags {
  const orgId = useOrgId();
  const plan = usePlan();

  const { data } = useQuery({
    queryKey: ["feature-flags", orgId, plan],
    queryFn: () =>
      apiClient
        .get(`/flags/evaluate-all?org_id=${orgId}&plan=${plan}`)
        .then((r) => r.data as FeatureFlags),
    enabled: !!orgId,
    staleTime: 5 * 60 * 1000,   // 5-minute cache
    refetchOnWindowFocus: false,
  });

  return data ?? DEFAULT_FLAGS;
}

export function useFlag(flagName: keyof FeatureFlags): boolean {
  const flags = useFeatureFlags();
  return flags[flagName] ?? false;
}
