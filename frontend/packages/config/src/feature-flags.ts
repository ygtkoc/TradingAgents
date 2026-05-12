/**
 * Static, build-time feature flags. Runtime flags should come from
 * `platform_settings` (server) and not from this file.
 */

export const featureFlags = {
  enableBilling:        false,
  enableShadowMode:     true,
  enableManualApproval: true,
  enableExportCsv:      false,
} as const;

export type FeatureFlag = keyof typeof featureFlags;
