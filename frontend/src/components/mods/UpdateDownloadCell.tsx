import { AlertTriangle, Download, ExternalLink, Package } from "lucide-react";
import { useEffect, useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";

import { Button } from "@/components/ui/Button";
import { DownloadProgress } from "@/components/ui/DownloadProgress";
import {
  useCancelDownload,
  useCheckConflicts,
  useInstallMod,
  useStartDownload,
  useUninstallMod,
} from "@/hooks/mutations";
import { api } from "@/lib/api-client";
import { useDownloadStore } from "@/stores/download-store";
import { toast } from "@/stores/toast-store";
import type { ConflictCheckResult, DownloadJobOut, ModUpdate } from "@/types/api";

interface Props {
  update: ModUpdate;
  gameName: string;
  downloadJobs: DownloadJobOut[];
}

export function UpdateDownloadCell({ update, gameName, downloadJobs }: Props) {
  const startDownload = useStartDownload();
  const cancelDownload = useCancelDownload();
  const installMod = useInstallMod();
  const uninstallMod = useUninstallMod();
  const checkConflicts = useCheckConflicts();
  const storeJobs = useDownloadStore((s) => s.jobs);
  const [conflicts, setConflicts] = useState<ConflictCheckResult | null>(null);
  const [installingFile, setInstallingFile] = useState<string | null>(null);

  const activeJob =
    downloadJobs.find(
      (j) =>
        j.nexus_mod_id === update.nexus_mod_id &&
        (j.status === "downloading" || j.status === "pending"),
    ) ??
    Object.values(storeJobs).find(
      (j) =>
        j.nexus_mod_id === update.nexus_mod_id &&
        (j.status === "downloading" || j.status === "pending"),
    );

  const completedJob =
    downloadJobs.find(
      (j) => j.nexus_mod_id === update.nexus_mod_id && j.status === "completed",
    ) ??
    Object.values(storeJobs).find(
      (j) => j.nexus_mod_id === update.nexus_mod_id && j.status === "completed",
    );

  // Close conflict dialog on Escape
  useEffect(() => {
    if (!conflicts) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setConflicts(null);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [conflicts]);

  const doInstall = async (fileName: string, skipConflicts: string[]) => {
    const oldArchive = update.source_archive;

    // Uninstall old version right before install (after conflict check)
    if (update.installed_mod_id) {
      await uninstallMod.mutateAsync({ gameName, modId: update.installed_mod_id });
    }
    await installMod.mutateAsync({
      gameName,
      data: { archive_filename: fileName, skip_conflicts: skipConflicts },
    });
    toast.success("Mod updated", update.display_name);

    // Auto-cleanup: silently delete old archive after successful update install
    if (oldArchive && oldArchive !== fileName) {
      api
        .delete(
          `/api/v1/games/${gameName}/install/archives/${encodeURIComponent(oldArchive)}`,
        )
        .catch(() => {});
    }
  };

  const handleInstall = async (fileName: string) => {
    setInstallingFile(fileName);
    try {
      const result = await checkConflicts.mutateAsync({
        gameName,
        archiveFilename: fileName,
      });

      if (result.conflicts.length > 0) {
        setConflicts(result);
      } else {
        await doInstall(fileName, []);
      }
    } catch {
      // Errors handled by mutation callbacks
    } finally {
      setInstallingFile(null);
    }
  };

  const handleInstallWithSkip = async () => {
    if (!conflicts) return;
    try {
      await doInstall(
        conflicts.archive_filename,
        conflicts.conflicts.map((c) => c.file_path),
      );
    } finally {
      setConflicts(null);
    }
  };

  const handleInstallOverwrite = async () => {
    if (!conflicts) return;
    try {
      await doInstall(conflicts.archive_filename, []);
    } finally {
      setConflicts(null);
    }
  };

  // Active download → show progress bar
  if (activeJob) {
    return (
      <div className="w-48">
        <DownloadProgress
          job={activeJob}
          onCancel={() => cancelDownload.mutate({ gameName, jobId: activeJob.id })}
        />
      </div>
    );
  }

  // Completed download → show Install button
  if (completedJob) {
    return (
      <>
        <Button
          variant="primary"
          size="sm"
          onClick={() => handleInstall(completedJob.file_name)}
          loading={
            installingFile === completedJob.file_name ||
            uninstallMod.isPending ||
            checkConflicts.isPending ||
            installMod.isPending
          }
        >
          <Package size={12} /> Install
        </Button>

        {conflicts && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div className="w-full max-w-lg rounded-xl border border-border bg-surface-1 p-6">
              <div className="mb-4 flex items-center gap-2 text-warning">
                <AlertTriangle size={20} />
                <h3 className="text-lg font-semibold text-text-primary">
                  File Conflicts Detected
                </h3>
              </div>
              <p className="mb-3 text-sm text-text-secondary">
                {conflicts.conflicts.length} file(s) conflict with installed mods:
              </p>
              <div className="mb-4 max-h-48 overflow-y-auto rounded border border-border bg-surface-0 p-3">
                {conflicts.conflicts.map((c) => (
                  <div key={c.file_path} className="py-1 text-xs">
                    <span className="font-mono text-text-primary">{c.file_path}</span>
                    <span className="ml-2 text-text-muted">(owned by {c.owning_mod_name})</span>
                  </div>
                ))}
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="secondary" size="sm" onClick={() => setConflicts(null)}>
                  Cancel
                </Button>
                <Button variant="secondary" size="sm" onClick={handleInstallWithSkip}>
                  Skip Conflicts
                </Button>
                <Button size="sm" onClick={handleInstallOverwrite}>
                  Overwrite
                </Button>
              </div>
            </div>
          </div>
        )}
      </>
    );
  }

  // No file_id → link to Nexus
  if (!update.nexus_file_id) {
    return (
      <button
        onClick={() => openUrl(update.nexus_url).catch(() => {})}
        className="inline-flex items-center gap-1 text-accent hover:underline text-xs"
      >
        <ExternalLink size={12} /> Nexus
      </button>
    );
  }

  // Default → Download button
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => {
        if (update.nexus_file_id) {
          startDownload.mutate({
            gameName,
            data: {
              nexus_mod_id: update.nexus_mod_id,
              nexus_file_id: update.nexus_file_id,
            },
          });
        }
      }}
      loading={startDownload.isPending}
    >
      <Download size={12} />
    </Button>
  );
}
