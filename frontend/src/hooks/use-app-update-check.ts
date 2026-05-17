import { useEffect, useRef, useState } from "react";

import { useModSummary } from "@/hooks/queries";
import { compareVersions, isNewerVersion, normalizeVersion } from "@/lib/version";

// Hard-coded because the Nexus mod ID + domain never change for RipperMod
// Manager's own listing. Mirrors the constants in SettingsPage.
export const RIPPERMOD_NEXUS_MOD_ID = 27781;
export const RIPPERMOD_NEXUS_DOMAIN = "cyberpunk2077";
export const RIPPERMOD_NEXUS_URL = `https://www.nexusmods.com/${RIPPERMOD_NEXUS_DOMAIN}/mods/${RIPPERMOD_NEXUS_MOD_ID}`;

const DISMISSED_KEY = "rmm.app_update.dismissed_version";

export interface AppUpdateState {
  currentVersion: string;
  latestVersion: string | null;
  hasUpdate: boolean;
  isLoading: boolean;
  nexusUrl: string;
  dismissed: boolean;
  dismiss: () => void;
}

/**
 * Polls the Nexus mod summary for RipperMod's own listing and compares the
 * published version against the build-time `__APP_VERSION__`. Returns
 * `hasUpdate=true` only when the Nexus version parses cleanly and is strictly
 * newer — a malformed Nexus version string can never produce a false positive.
 *
 * Compliance: read-only against the Nexus public API, never auto-downloads
 * or auto-installs. The UI surfaces a "View on Nexus" link the user clicks
 * manually, which is the Nexus-recommended distribution model.
 */
export function useAppUpdateCheck(): AppUpdateState {
  const currentVersion = __APP_VERSION__;
  const { data: summary, isLoading } = useModSummary(RIPPERMOD_NEXUS_MOD_ID);
  const latestVersion = summary?.version ?? null;

  const hasUpdate = latestVersion != null && isNewerVersion(currentVersion, latestVersion);

  // Dismissal persists per-version so a fresh release re-shows the banner
  // even if the user dismissed the previous one. Read on mount only; the
  // state setter handles subsequent updates so re-renders stay cheap.
  const dismissedVersion = readDismissed();
  const dismissed =
    hasUpdate && latestVersion != null
      ? compareVersions(dismissedVersion ?? "", latestVersion) >= 0
      : false;

  const [, force] = useState(0);
  const dismiss = () => {
    if (latestVersion) {
      try {
        localStorage.setItem(DISMISSED_KEY, normalizeVersion(latestVersion));
      } catch {
        // localStorage may be unavailable in some Tauri contexts; ignore.
      }
      force((n) => n + 1);
    }
  };

  return {
    currentVersion,
    latestVersion,
    hasUpdate,
    isLoading,
    nexusUrl: RIPPERMOD_NEXUS_URL,
    dismissed,
    dismiss,
  };
}

function readDismissed(): string | null {
  try {
    return localStorage.getItem(DISMISSED_KEY);
  } catch {
    return null;
  }
}

/**
 * Fires a one-time toast on app startup when a new version is available and
 * has not already been dismissed for that specific version. Should be mounted
 * once at the app root.
 */
export function useAppUpdateStartupToast(
  state: AppUpdateState,
  toast: (title: string, message: string) => void,
) {
  // Ref-based latch so the synchronous setter avoids the cascading-render lint
  // (`react-hooks/set-state-in-effect`). The toast only fires once per app
  // session anyway, so we never need to re-render based on this flag.
  const fired = useRef(false);
  useEffect(() => {
    if (fired.current) return;
    if (state.isLoading) return;
    if (!state.hasUpdate || state.dismissed) return;
    toast(
      "RipperMod Manager update available",
      `Version ${state.latestVersion} is on Nexus Mods. Open Settings or click the banner to view.`,
    );
    fired.current = true;
  }, [state.isLoading, state.hasUpdate, state.dismissed, state.latestVersion, toast]);
}
