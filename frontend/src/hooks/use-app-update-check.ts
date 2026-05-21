import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api } from "@/lib/api-client";
import { isNewerVersion } from "@/lib/version";
import type { ModSummary } from "@/types/api";

export const RIPPERMOD_NEXUS_MOD_ID = 27781;
export const RIPPERMOD_NEXUS_DOMAIN = "cyberpunk2077";
export const RIPPERMOD_NEXUS_URL = `https://www.nexusmods.com/${RIPPERMOD_NEXUS_DOMAIN}/mods/${RIPPERMOD_NEXUS_MOD_ID}`;
export const RIPPERMOD_NEXUS_FILES_URL = `${RIPPERMOD_NEXUS_URL}?tab=files`;

export interface AppUpdateState {
  currentVersion: string;
  latestVersion: string | null;
  hasUpdate: boolean;
  isLoading: boolean;
  nexusUrl: string;
  nexusFilesUrl: string;
}

/**
 * Polls the Nexus mod summary for RipperMod's own listing and compares the
 * published version against the build-time `__APP_VERSION__`. Returns
 * `hasUpdate=true` only when the Nexus version parses cleanly and is strictly
 * newer — a malformed Nexus version string can never produce a false positive.
 *
 * Compliance: read-only against the Nexus public API. Surfaces an update
 * notification; the actual install is always user-initiated (manual run of
 * the installer), per the Nexus Edition compliance contract.
 */
export function useAppUpdateCheck(): AppUpdateState {
  const currentVersion = __APP_VERSION__;
  const { data: summary, isLoading } = useQuery<ModSummary>({
    queryKey: ["mod-summary-fresh", RIPPERMOD_NEXUS_MOD_ID],
    queryFn: () =>
      api.get(`/api/v1/nexus/mods/${RIPPERMOD_NEXUS_MOD_ID}/summary?fresh=true`),
    staleTime: 30 * 60 * 1000,
    retry: false,
  });
  const latestVersion = summary?.version ?? null;

  const hasUpdate = latestVersion != null && isNewerVersion(currentVersion, latestVersion);

  return {
    currentVersion,
    latestVersion,
    hasUpdate,
    isLoading,
    nexusUrl: RIPPERMOD_NEXUS_URL,
    nexusFilesUrl: RIPPERMOD_NEXUS_FILES_URL,
  };
}

/**
 * Fires a one-time toast on app startup when a new version is available.
 * Should be mounted once at the app root.
 */
export function useAppUpdateStartupToast(
  state: AppUpdateState,
  toast: (title: string, message: string) => void,
) {
  const fired = useRef(false);
  useEffect(() => {
    if (fired.current) return;
    if (state.isLoading) return;
    if (!state.hasUpdate) return;
    toast(
      "RipperMod Manager update available",
      `Version ${state.latestVersion} is on Nexus Mods. Open Settings or click the banner to view.`,
    );
    fired.current = true;
  }, [state.isLoading, state.hasUpdate, state.latestVersion, toast]);
}
