import {
  ArrowUpCircle,
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
  isUpdate?: boolean;
  updateVersion?: string;
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
  isUpdate,
  updateVersion,
  onInstall,
  onInstallByFilename,
  onDownload,
  onCancelDownload,
}: Props) {
  const stopPropagation = (e: React.MouseEvent) => e.stopPropagation();

  if (isInstalled) {
    return (
      <div onClick={stopPropagation}>
        <Badge variant="success">
          <Check size={10} /> Installed
        </Badge>
      </div>
    );
  }

  if (isInstalling) {
    return (
      <span onClick={stopPropagation} className="inline-flex items-center gap-1 text-xs text-text-muted">
        <Loader2 size={12} className="animate-spin" /> Installing...
      </span>
    );
  }

  if (activeDownload) {
    return (
      <div className="w-36" onClick={stopPropagation}>
        <DownloadProgress job={activeDownload} onCancel={onCancelDownload} />
      </div>
    );
  }

  if (completedDownload) {
    return (
      <button
        onClick={(e) => { e.stopPropagation(); onInstallByFilename(); }}
        title={isUpdate ? `Install update${updateVersion ? ` v${updateVersion}` : ""} from: ${completedDownload.file_name}` : `Install from downloaded file: ${completedDownload.file_name}`}
        className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-white hover:opacity-80 ${isUpdate ? "bg-warning text-black" : "bg-accent"}`}
      >
        {isUpdate ? <ArrowUpCircle size={12} /> : <Package size={12} />}
        {isUpdate ? "Install Update" : "Install"}
      </button>
    );
  }

  if (archive) {
    return (
      <button
        onClick={(e) => { e.stopPropagation(); onInstall(); }}
        disabled={hasConflicts}
        className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-white hover:opacity-80 disabled:opacity-50 ${isUpdate ? "bg-warning text-black" : "bg-accent"}`}
        title={isUpdate ? `Install update${updateVersion ? ` v${updateVersion}` : ""} from ${archive.filename}` : `Install from ${archive.filename}`}
      >
        {isUpdate ? <ArrowUpCircle size={12} /> : <Download size={12} />}
        {isUpdate ? "Install Update" : "Install"}
      </button>
    );
  }

  return (
    <div className="flex items-center gap-1" onClick={stopPropagation}>
      <button
        onClick={onDownload}
        disabled={isDownloading}
        title={isUpdate ? `Download update${updateVersion ? ` v${updateVersion}` : ""} from Nexus` : "Download this mod from Nexus"}
        className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-white hover:opacity-80 disabled:opacity-50 ${isUpdate ? "bg-warning text-black" : "bg-accent"}`}
      >
        {isDownloading ? (
          <Loader2 size={12} className="animate-spin" />
        ) : isUpdate ? (
          <ArrowUpCircle size={12} />
        ) : (
          <Download size={12} />
        )}
        {isUpdate ? "Update" : "Download"}
      </button>
      {nexusUrl && (
        <button
          onClick={() => openUrl(nexusUrl).catch(() => {})}
          title="Open mod page on Nexus Mods"
          className="inline-flex items-center gap-1 rounded-md bg-surface-2 px-2 py-1 text-xs font-medium text-text-secondary hover:bg-surface-2/80 border border-border"
        >
          <ExternalLink size={12} />
        </button>
      )}
    </div>
  );
}
