import { CheckCircle2, Download, ExternalLink, FolderOpen, X } from "lucide-react";
import { openPath, openUrl } from "@tauri-apps/plugin-opener";

import { type AppUpdateState } from "@/hooks/use-app-update-check";
import {
  useAppUpdateDownloadStatus,
  useCancelAppUpdateDownload,
  useStartAppUpdateDownload,
} from "@/hooks/use-app-update-download";
import { useSettings } from "@/hooks/queries";
import { cn } from "@/lib/utils";
import { toast } from "@/stores/toast-store";

interface Props {
  update: AppUpdateState;
  size?: "sm" | "md";
}

/**
 * Actions block shared by the top banner and the Settings notice.
 *
 * Premium users: in-app download (via Nexus API) → "Open folder to install"
 * once ready. The .exe is never auto-launched — the user closes the app and
 * runs the installer themselves, per the Nexus auto-update policy.
 *
 * Free users: deep-link straight to the Nexus Files tab so they can grab the
 * installer from the browser.
 */
export function AppUpdateActions({ update, size = "md" }: Props) {
  const { data: settings = [] } = useSettings();
  const isPremium = settings.find((s) => s.key === "nexus_is_premium")?.value === "true";

  const { data: download } = useAppUpdateDownloadStatus();
  const startDownload = useStartAppUpdateDownload();
  const cancelDownload = useCancelAppUpdateDownload();

  const handleDownload = () => {
    startDownload.mutate(undefined, {
      onError: () => toast.error("Update download failed", "Could not start download"),
    });
  };

  const handleOpenFolder = () => {
    if (!download?.path) return;
    const folder = download.path.replace(/[\\/][^\\/]+$/, "");
    openPath(folder).catch((e) => toast.error("Could not open folder", String(e)));
  };

  const handleViewOnNexus = () => {
    void openUrl(update.nexusUrl);
  };

  const handleGetOnNexus = () => {
    void openUrl(update.nexusFilesUrl);
  };

  const baseBtn = cn(
    "inline-flex shrink-0 items-center gap-1 rounded-md border font-medium transition-colors",
    size === "sm" ? "px-2 py-1 text-xs" : "px-2.5 py-1 text-xs",
  );

  const accentBtn = cn(baseBtn, "border-accent/40 bg-accent/15 text-accent hover:bg-accent/25");
  const ghostBtn = cn(baseBtn, "border-border/60 bg-surface-2 text-text-secondary hover:bg-surface-1 hover:text-text-primary");

  if (download?.state === "ready") {
    return (
      <div className="flex shrink-0 items-center gap-1.5">
        <span className="inline-flex items-center gap-1 text-xs text-accent">
          <CheckCircle2 size={12} /> Installer ready
        </span>
        <button type="button" onClick={handleOpenFolder} className={accentBtn}>
          <FolderOpen size={12} /> Open folder
        </button>
      </div>
    );
  }

  if (download?.state === "downloading") {
    const pct =
      download.total_bytes > 0
        ? Math.min(100, Math.round((download.downloaded_bytes / download.total_bytes) * 100))
        : 0;
    return (
      <div className="flex shrink-0 items-center gap-1.5">
        <span className="text-xs text-text-secondary tabular-nums">{pct}%</span>
        <button
          type="button"
          onClick={() => cancelDownload.mutate()}
          className={ghostBtn}
          aria-label="Cancel download"
        >
          <X size={12} /> Cancel
        </button>
      </div>
    );
  }

  if (download?.state === "error" && download.error_code !== "premium_required") {
    return (
      <div className="flex shrink-0 items-center gap-1.5">
        <span className="text-xs text-danger" title={download.error_message ?? undefined}>
          Download failed
        </span>
        <button type="button" onClick={handleDownload} className={ghostBtn} disabled={startDownload.isPending}>
          <Download size={12} /> Retry
        </button>
        <button type="button" onClick={handleViewOnNexus} className={accentBtn}>
          <ExternalLink size={12} /> View on Nexus
        </button>
      </div>
    );
  }

  if (!isPremium || download?.error_code === "premium_required") {
    return (
      <button type="button" onClick={handleGetOnNexus} className={accentBtn}>
        <ExternalLink size={12} /> Get on Nexus
      </button>
    );
  }

  return (
    <div className="flex shrink-0 items-center gap-1.5">
      <button
        type="button"
        onClick={handleDownload}
        disabled={startDownload.isPending}
        className={accentBtn}
      >
        <Download size={12} /> Download update
      </button>
      <button type="button" onClick={handleViewOnNexus} className={ghostBtn}>
        <ExternalLink size={12} /> View on Nexus
      </button>
    </div>
  );
}
