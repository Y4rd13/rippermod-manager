import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import type { SaveBackupActionResult, SaveBackupStatus } from "@/types/api";

const BASE = "/api/v1/save-backups";
const KEY = ["save-backups"];

export function useSaveBackups() {
  return useQuery<SaveBackupStatus, Error>({
    queryKey: KEY,
    queryFn: () => api.get<SaveBackupStatus>(`${BASE}/`),
  });
}

export function useBackupNow() {
  const qc = useQueryClient();
  return useMutation<SaveBackupActionResult, Error, void>({
    mutationFn: () => api.post<SaveBackupActionResult>(`${BASE}/backup-now`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useRestoreSaveBackup() {
  const qc = useQueryClient();
  return useMutation<SaveBackupActionResult, Error, string>({
    mutationFn: (id) => api.post<SaveBackupActionResult>(`${BASE}/restore`, { id }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useSetSaveBackupEnabled() {
  const qc = useQueryClient();
  return useMutation<unknown, Error, boolean>({
    mutationFn: (enabled) =>
      api.put("/api/v1/settings/", {
        settings: { save_backup_enabled: enabled ? "true" : "false" },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
      void qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}

export function useSetSaveBackupPath() {
  const qc = useQueryClient();
  // An empty string clears the override → the backend falls back to the default path.
  return useMutation<unknown, Error, string | null>({
    mutationFn: (path) =>
      api.put("/api/v1/settings/", { settings: { save_backup_path: path ?? "" } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
  });
}
