import { useCallback, useEffect, useMemo, useState } from "react";

import {
  useCancelDownload,
  useCheckConflicts,
  useInstallMod,
  useStartModDownload,
} from "@/hooks/mutations";
import type { AvailableArchive, ConflictCheckResult, DownloadJobOut } from "@/types/api";

export function useInstallFlow(
  gameName: string,
  archives: AvailableArchive[],
  downloadJobs: DownloadJobOut[] = [],
) {
  const [installingModIds, setInstallingModIds] = useState<Set<number>>(new Set());
  const [downloadingModId, setDownloadingModId] = useState<number | null>(null);
  const [conflicts, setConflicts] = useState<ConflictCheckResult | null>(null);
  const [conflictModId, setConflictModId] = useState<number | null>(null);
  const [fomodArchive, setFomodArchive] = useState<string | null>(null);

  const installMod = useInstallMod();
  const checkConflicts = useCheckConflicts();
  const startModDownload = useStartModDownload();
  const cancelDownload = useCancelDownload();

  const archiveByModId = useMemo(() => {
    const map = new Map<number, AvailableArchive>();
    for (const a of archives) {
      if (a.nexus_mod_id == null) continue;
      const existing = map.get(a.nexus_mod_id);
      if (!existing || a.size > existing.size) {
        map.set(a.nexus_mod_id, a);
      }
    }
    return map;
  }, [archives]);

  const activeDownloadByModId = useMemo(() => {
    const map = new Map<number, DownloadJobOut>();
    for (const job of downloadJobs) {
      if (job.status === "downloading" || job.status === "pending") {
        map.set(job.nexus_mod_id, job);
      }
    }
    return map;
  }, [downloadJobs]);

  const completedDownloadByModId = useMemo(() => {
    const map = new Map<number, DownloadJobOut>();
    for (const job of downloadJobs) {
      if (job.status === "completed") {
        map.set(job.nexus_mod_id, job);
      }
    }
    return map;
  }, [downloadJobs]);

  const addInstalling = useCallback(
    (id: number) => setInstallingModIds((prev) => new Set(prev).add(id)),
    [],
  );

  const removeInstalling = useCallback(
    (id: number) =>
      setInstallingModIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      }),
    [],
  );

  useEffect(() => {
    if (!conflicts) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (conflictModId != null) removeInstalling(conflictModId);
        setConflicts(null);
        setConflictModId(null);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [conflicts, conflictModId, removeInstalling]);

  const doInstall = useCallback(
    async (fileName: string, skipConflicts: string[], nexusModId: number) => {
      try {
        await installMod.mutateAsync({
          gameName,
          data: { archive_filename: fileName, skip_conflicts: skipConflicts },
        });
      } finally {
        removeInstalling(nexusModId);
      }
    },
    [gameName, installMod, removeInstalling],
  );

  const handleInstall = useCallback(
    async (nexusModId: number, archive: AvailableArchive) => {
      addInstalling(nexusModId);
      try {
        const result = await checkConflicts.mutateAsync({
          gameName,
          archiveFilename: archive.filename,
        });

        if (result.is_fomod) {
          setFomodArchive(archive.filename);
          removeInstalling(nexusModId);
          return;
        }

        if (result.conflicts.length > 0) {
          setConflicts(result);
          setConflictModId(nexusModId);
        } else {
          await doInstall(archive.filename, [], nexusModId);
        }
      } catch {
        removeInstalling(nexusModId);
      }
    },
    [gameName, addInstalling, removeInstalling, checkConflicts, doInstall],
  );

  const handleInstallByFilename = useCallback(
    async (nexusModId: number, fileName: string) => {
      addInstalling(nexusModId);
      try {
        const result = await checkConflicts.mutateAsync({
          gameName,
          archiveFilename: fileName,
        });

        if (result.is_fomod) {
          setFomodArchive(fileName);
          removeInstalling(nexusModId);
          return;
        }

        if (result.conflicts.length > 0) {
          setConflicts(result);
          setConflictModId(nexusModId);
        } else {
          await doInstall(fileName, [], nexusModId);
        }
      } catch {
        removeInstalling(nexusModId);
      }
    },
    [gameName, addInstalling, removeInstalling, checkConflicts, doInstall],
  );

  const handleInstallWithSkip = useCallback(async () => {
    if (!conflicts || conflictModId == null) return;
    try {
      await doInstall(
        conflicts.archive_filename,
        conflicts.conflicts.map((c) => c.file_path),
        conflictModId,
      );
    } finally {
      setConflicts(null);
      setConflictModId(null);
    }
  }, [conflicts, conflictModId, doInstall]);

  const handleInstallOverwrite = useCallback(async () => {
    if (!conflicts || conflictModId == null) return;
    try {
      await doInstall(conflicts.archive_filename, [], conflictModId);
    } finally {
      setConflicts(null);
      setConflictModId(null);
    }
  }, [conflicts, conflictModId, doInstall]);

  const dismissConflicts = useCallback(() => {
    if (conflictModId != null) removeInstalling(conflictModId);
    setConflicts(null);
    setConflictModId(null);
  }, [conflictModId, removeInstalling]);

  const dismissFomod = useCallback(() => {
    setFomodArchive(null);
  }, []);

  const handleDownload = useCallback(
    (nexusModId: number) => {
      setDownloadingModId(nexusModId);
      startModDownload.mutate(
        { gameName, nexusModId },
        { onSettled: () => setDownloadingModId(null) },
      );
    },
    [gameName, startModDownload],
  );

  const handleCancelDownload = useCallback(
    (jobId: number) => {
      cancelDownload.mutate({ gameName, jobId });
    },
    [gameName, cancelDownload],
  );

  return {
    archiveByModId,
    installingModIds,
    downloadingModId,
    conflicts,
    fomodArchive,
    activeDownloadByModId,
    completedDownloadByModId,
    handleInstall,
    handleInstallByFilename,
    handleInstallWithSkip,
    handleInstallOverwrite,
    dismissConflicts,
    dismissFomod,
    handleDownload,
    handleCancelDownload,
  };
}
