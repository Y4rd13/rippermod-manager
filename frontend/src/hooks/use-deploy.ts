import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api } from "@/lib/api-client";
import { REDMOD_MISSING_MESSAGE, REDMOD_MISSING_REASON } from "@/lib/deploy-toast";
import { toast } from "@/stores/toast-store";

export interface DriftReport {
  total: number;
  linked: number;
  missing: number;
  foreign: number;
  by_mod: Record<string, { linked: number; missing: number; foreign: number }>;
}

export interface DeployOpResult {
  op: {
    operation: string;
    src: string;
    dst: string;
    installed_mod_id: number | null;
    relative_path: string;
  };
  /** foreign: the destination was not this mod's link, so it was left in place. */
  status: "done" | "failed" | "foreign";
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

export interface RedmodDeployResult {
  ran: boolean;
  success: boolean;
  skipped_reason: string;
  returncode: number | null;
  stdout: string;
  stderr: string;
  error: string;
}

export interface DeployReport {
  total: number;
  done: number;
  failed: number;
  foreign: number;
  skipped_existing: number;
  results: DeployOpResult[];
  preflight: PreflightReport | null;
  redmod: RedmodDeployResult | null;
  /** Files a force deploy moved aside that could not go back: their path is occupied. */
  displaced_not_restored: string[];
  /** Deploy traces a clean undeploy deleted (modlist.txt, r6/cache/modded). */
  removed_paths: string[];
}

/** Background REDmod compile state for one game (toggle, uninstall, profile load). */
export interface RedmodStatus {
  state: "idle" | "compiling";
  last_result: RedmodDeployResult | null;
  last_finished_at: string | null;
}

/** Game-dir paths a force deploy would move aside to `<mods_dir>/_displaced/`. */
export interface ForcePreview {
  paths: string[];
}

const deployPath = (gameName: string) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/install/deploy`;
const undeployPath = (gameName: string) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/install/undeploy`;
const statusPath = (gameName: string) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/install/deploy/status`;
const forcePreviewPath = (gameName: string) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/install/deploy/force-preview`;
const redmodStatusPath = (gameName: string) =>
  `/api/v1/games/${encodeURIComponent(gameName)}/install/redmod/status`;
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

/**
 * Background REDmod compile state. Polls every 1.5 s only while a compile is
 * running; toggle, uninstall and profile load invalidate it to start polling.
 */
export function useRedmodStatus(gameName: string | null) {
  return useQuery<RedmodStatus, Error>({
    queryKey: ["redmod-status", gameName],
    queryFn: () => api.get<RedmodStatus>(redmodStatusPath(gameName!)),
    enabled: !!gameName,
    refetchInterval: (query) => (query.state.data?.state === "compiling" ? 1500 : false),
  });
}

/**
 * Watches background REDmod compiles and toasts their outcome: a failed compile
 * shows its error, a missing redMod.exe shows ``REDMOD_MISSING_MESSAGE``.
 * Results that already existed when the game was first seen are not toasted.
 * Returns true while a compile is running.
 */
export function useRedmodCompileWatcher(gameName: string | null): boolean {
  const { data } = useRedmodStatus(gameName);
  const seen = useRef<{ game: string | null; finishedAt: string | null } | null>(null);

  useEffect(() => {
    if (!data) return;
    const finishedAt = data.last_finished_at;
    const prev = seen.current;
    seen.current = { game: gameName, finishedAt };
    if (prev === null || prev.game !== gameName) return;
    if (!finishedAt || finishedAt === prev.finishedAt) return;
    const result = data.last_result;
    if (!result) return;
    if (result.ran && !result.success) {
      toast.error("REDmod compile failed", result.error || "redmod deploy returned an error");
    } else if (!result.ran && result.skipped_reason === REDMOD_MISSING_REASON) {
      toast.warning("REDmod not compiled", REDMOD_MISSING_MESSAGE);
    }
  }, [data, gameName]);

  return data?.state === "compiling";
}

/**
 * What a force deploy would move aside. Only fetched while ``enabled`` (the
 * confirmation dialog is open) and never cached, so it reflects the disk now.
 */
export function useForcePreview(gameName: string | null, enabled: boolean) {
  return useQuery<ForcePreview, Error>({
    queryKey: ["force-preview", gameName],
    queryFn: () => api.get<ForcePreview>(forcePreviewPath(gameName!)),
    enabled: !!gameName && enabled,
    staleTime: 0,
    gcTime: 0,
  });
}

/**
 * Trigger a deploy. Pass ``{ force: true }`` to move foreign files
 * (copy-installed leftovers from other mod managers) aside to
 * ``<mods_dir>/_displaced/`` instead of failing with "destination exists";
 * undeploy puts them back. Default: ``{ force: false }``.
 */
export function useDeploy(gameName: string | null) {
  const qc = useQueryClient();
  return useMutation<DeployReport, Error, { force?: boolean } | void>({
    mutationFn: (vars) => {
      const force = (vars && "force" in vars && vars.force) ?? false;
      const url = force
        ? `${deployPath(gameName!)}?force=true`
        : deployPath(gameName!);
      return api.post<DeployReport>(url);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["deploy-status", gameName] });
      void qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      void qc.invalidateQueries({ queryKey: ["health", gameName] });
    },
  });
}

export function useUndeploy(gameName: string | null) {
  const qc = useQueryClient();
  return useMutation<DeployReport, Error, void>({
    mutationFn: () => api.post<DeployReport>(undeployPath(gameName!)),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["deploy-status", gameName] });
      void qc.invalidateQueries({ queryKey: ["health", gameName] });
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
