import {
  Check,
  Download,
  ExternalLink,
  Loader2,
  Package,
} from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { Badge } from "@/components/ui/Badge";
import { DownloadProgress } from "@/components/ui/DownloadProgress";
import type { AvailableArchive, DownloadJobOut } from "@/types/api";

interface Props {
  isInstalled: boolean;
  isInstalling: boolean;
  activeDownload?: DownloadJobOut;
  completedDownload?: DownloadJobOut;
  archive?: AvailableArchive;
  nexusUrl?: string;
  hasConflicts: boolean;
  isDownloading: boolean;
  onInstall: () => void;
  onInstallByFilename: () => void;
  onDownload: () => void;
  onCancelDownload: () => void;
}

export function ModCardAction({
  isInstalled,
  isInstalling,
  activeDownload,
  completedDownload,
  archive,
  nexusUrl,
  hasConflicts,
  isDownloading,
  onInstall,
  onInstallByFilename,
  onDownload,
  onCancelDownload,
}: Props) {
  if (isInstalled) {
    return (
      <Badge variant="success">
        <Check size={10} /> Installed
      </Badge>
    );
  }

  if (isInstalling) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-text-muted">
        <Loader2 size={12} className="animate-spin" /> Installing...
      </span>
    );
  }

  if (activeDownload) {
    return (
      <div className="w-36">
        <DownloadProgress job={activeDownload} onCancel={onCancelDownload} />
      </div>
    );
  }

  if (completedDownload) {
    return (
      <button
        onClick={onInstallByFilename}
        className="inline-flex items-center gap-1 rounded-md bg-accent px-2 py-1 text-xs font-medium text-white hover:bg-accent/80"
      >
        <Package size={12} />
        Install
      </button>
    );
  }

  if (archive) {
    return (
      <button
        onClick={onInstall}
        disabled={hasConflicts}
        className="inline-flex items-center gap-1 rounded-md bg-accent px-2 py-1 text-xs font-medium text-white hover:bg-accent/80 disabled:opacity-50"
        title={`Install from ${archive.filename}`}
      >
        <Download size={12} />
        Install
      </button>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={onDownload}
        disabled={isDownloading}
        className="inline-flex items-center gap-1 rounded-md bg-accent px-2 py-1 text-xs font-medium text-white hover:bg-accent/80 disabled:opacity-50"
      >
        {isDownloading ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
        Download
      </button>
      {nexusUrl && (
        <button
          onClick={() => openUrl(nexusUrl).catch(() => {})}
          className="inline-flex items-center gap-1 rounded-md bg-surface-2 px-2 py-1 text-xs font-medium text-text-secondary hover:bg-surface-2/80 border border-border"
        >
          <ExternalLink size={12} />
        </button>
      )}
    </div>
  );
}
