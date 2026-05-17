import { ExternalLink, Sparkles, X } from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { useAppUpdateCheck } from "@/hooks/use-app-update-check";

/**
 * Top-of-app dismissible banner. Renders only when the latest Nexus version
 * is strictly newer than the running build AND the user hasn't already
 * dismissed that specific version. Dismissal persists in localStorage keyed
 * by the version string so a new release re-shows the banner automatically.
 */
export function AppUpdateBanner() {
  const update = useAppUpdateCheck();

  if (!update.hasUpdate || update.dismissed) return null;

  const handleView = () => {
    void openUrl(update.nexusUrl);
  };

  return (
    <div className="flex items-center justify-between gap-3 border-b border-accent/30 bg-accent/10 px-4 py-2 text-sm">
      <div className="flex items-center gap-2 text-text-primary">
        <Sparkles size={14} className="shrink-0 text-accent" />
        <span>
          <strong className="font-semibold">RipperMod Manager v{update.latestVersion}</strong>{" "}
          is available on Nexus Mods.
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          onClick={handleView}
          className="inline-flex items-center gap-1 rounded-md border border-accent/40 bg-accent/15 px-2.5 py-1 text-xs font-medium text-accent transition-colors hover:bg-accent/25"
        >
          <ExternalLink size={12} />
          View on Nexus
        </button>
        <button
          type="button"
          onClick={update.dismiss}
          aria-label="Dismiss until next update"
          title="Dismiss until next update"
          className="rounded-md p-1 text-text-muted transition-colors hover:bg-surface-2 hover:text-text-primary"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
