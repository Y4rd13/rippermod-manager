import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api-client";

export interface DriftReport {
  total: number;
  linked: number;
  missing: number;
  foreign: number;
  by_mod: Record<string, { linked: number; missing: number; foreign: number }>;
}

export interface DeployOpResult {
  op: { operation: string; src: string; dst: string; installed_mod_id: number | null };
  status: "done" | "failed";
  error: string;
}

export interface PreflightReport {
  ok: boolean;
  reasons: string[];
  game_running: boolean;
  hardlink_supported: boolean;
  same_volume: boolean;
  free_disk_bytes: number;
}

export interface DeployReport {
  total: number;
  done: number;
  failed: number;
  skipped_existing: number;
  results: DeployOpResult[];
  preflight: PreflightReport | null;
}

export interface MigrationReport {
  migrated_mods: number;
  migrated_files: number;
  skipped_files: number;
  errors: string[];
}

const deployPath = (gameName: string) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/install/deploy`;
const undeployPath = (gameName: string) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/install/undeploy`;
const statusPath = (gameName: string) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/install/deploy/status`;
const migratePath = (gameName: string) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/install/migrate-to-vfs`;
const untrackedPath = (gameName: string) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/install/untracked-files`;

export function useDeployStatus(gameName: string | null) {
  return useQuery<DriftReport, Error>({
    queryKey: ["deploy-status", gameName],
    queryFn: () => api.get<DriftReport>(statusPath(gameName!)),
    enabled: !!gameName,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });
}

export function useDeploy(gameName: string | null) {
  const qc = useQueryClient();
  return useMutation<DeployReport, Error, void>({
    mutationFn: () => api.post<DeployReport>(deployPath(gameName!)),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["deploy-status", gameName] });
      void qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
    },
  });
}

export function useUndeploy(gameName: string | null) {
  const qc = useQueryClient();
  return useMutation<DeployReport, Error, void>({
    mutationFn: () => api.post<DeployReport>(undeployPath(gameName!)),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["deploy-status", gameName] });
    },
  });
}

export function useMigrateToVfs(gameName: string | null) {
  const qc = useQueryClient();
  return useMutation<MigrationReport, Error, void>({
    mutationFn: () => api.post<MigrationReport>(migratePath(gameName!)),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["deploy-status", gameName] });
      void qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
    },
  });
}

export function useUntrackedFiles(gameName: string | null) {
  return useQuery<{ files: string[] }, Error>({
    queryKey: ["untracked-files", gameName],
    queryFn: () => api.get<{ files: string[] }>(untrackedPath(gameName!)),
    enabled: !!gameName,
  });
}
