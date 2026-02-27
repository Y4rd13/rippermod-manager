import {
  ArrowUpCircle,
  Check,
  ChevronDown,
  Download,
  ExternalLink,
  Loader2,
  Package,
  Settings2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
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
  onInstallWithPreview?: () => void;
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
  onInstallWithPreview,
}: Props) {
  const stopPropagation = (e: React.MouseEvent) => e.stopPropagation();
  const [menuPos, setMenuPos] = useState<{ top: number; left: number } | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const chevronRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const handleChevronClick = () => {
    if (menuPos) {
      setMenuPos(null);
      return;
    }
    const rect = chevronRef.current?.getBoundingClientRect();
    if (rect) {
      setMenuPos({ top: rect.bottom + 4, left: rect.right - 160 });
    }
  };

  useEffect(() => {
    if (!menuPos) return;
    const handleClick = (e: MouseEvent) => {
      if (
        wrapperRef.current?.contains(e.target as Node) ||
        menuRef.current?.contains(e.target as Node)
      ) return;
      setMenuPos(null);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuPos]);

  const dropdownMenu = menuPos && onInstallWithPreview
    ? createPortal(
        <div
          ref={menuRef}
          className="fixed z-50 min-w-[160px] rounded-md border border-border bg-surface-1 py-1 shadow-lg"
          style={{ top: menuPos.top, left: menuPos.left }}
        >
          <button
            onClick={() => {
              setMenuPos(null);
              onInstallWithPreview();
            }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-text-secondary hover:bg-surface-2 hover:text-text-primary"
          >
            <Settings2 size={12} />
            Install with Options
          </button>
        </div>,
        document.body,
      )
    : null;

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
    const showSplit = !!onInstallWithPreview;

    return (
      <>
        <div className="inline-flex items-center" ref={wrapperRef} onClick={stopPropagation}>
          <button
            onClick={onInstallByFilename}
            title={isUpdate ? `Install update${updateVersion ? ` v${updateVersion}` : ""} from: ${completedDownload.file_name}` : `Install from downloaded file: ${completedDownload.file_name}`}
            className={`inline-flex items-center gap-1 ${showSplit ? "rounded-l-md" : "rounded-md"} px-2 py-1 text-xs font-medium text-white hover:opacity-80 ${isUpdate ? "bg-warning text-black" : "bg-accent"}`}
          >
            {isUpdate ? <ArrowUpCircle size={12} /> : <Package size={12} />}
            {isUpdate ? "Install Update" : "Install"}
          </button>
          {showSplit && (
            <button
              ref={chevronRef}
              onClick={handleChevronClick}
              className={`inline-flex items-center self-stretch rounded-r-md border-l border-white/20 px-1 text-xs font-medium text-white hover:opacity-80 ${isUpdate ? "bg-warning text-black" : "bg-accent"}`}
              title="Install options"
              aria-label="Install options"
            >
              <ChevronDown size={12} />
            </button>
          )}
        </div>
        {dropdownMenu}
      </>
    );
  }

  if (archive && !archive.is_empty) {
    const showSplit = !!onInstallWithPreview;

    return (
      <>
        <div className="inline-flex items-center" ref={wrapperRef} onClick={stopPropagation}>
          <button
            onClick={onInstall}
            disabled={hasConflicts}
            className={`inline-flex items-center gap-1 ${showSplit ? "rounded-l-md" : "rounded-md"} px-2 py-1 text-xs font-medium text-white hover:opacity-80 disabled:opacity-50 ${isUpdate ? "bg-warning text-black" : "bg-accent"}`}
            title={isUpdate ? `Install update${updateVersion ? ` v${updateVersion}` : ""} from ${archive.filename}` : `Install from ${archive.filename}`}
          >
            {isUpdate ? <ArrowUpCircle size={12} /> : <Download size={12} />}
            {isUpdate ? "Install Update" : "Install"}
          </button>
          {showSplit && (
            <button
              ref={chevronRef}
              onClick={handleChevronClick}
              disabled={hasConflicts}
              className={`inline-flex items-center self-stretch rounded-r-md border-l border-white/20 px-1 text-xs font-medium text-white hover:opacity-80 disabled:opacity-50 ${isUpdate ? "bg-warning text-black" : "bg-accent"}`}
              title="Install options"
              aria-label="Install options"
            >
              <ChevronDown size={12} />
            </button>
          )}
        </div>
        {dropdownMenu}
      </>
    );
  }

  return (
    <div className="flex items-center gap-1" onClick={stopPropagation}>
      <button
        onClick={onDownload}
        disabled={isDownloading}
        title={isUpdate ? `Download update${updateVersion ? ` v${updateVersion}` : ""} from Nexus` : "Download this mod from Nexus"}
        className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium disabled:opacity-50 ${isUpdate ? "bg-warning text-black hover:opacity-80" : "border border-accent text-accent hover:bg-accent/10"}`}
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
          aria-label="Open on Nexus Mods"
          className="inline-flex items-center gap-1 rounded-md bg-surface-2 px-2 py-1 text-xs font-medium text-text-secondary hover:bg-surface-2/80 border border-border"
        >
          <ExternalLink size={12} />
        </button>
      )}
    </div>
  );
}
