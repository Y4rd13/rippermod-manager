import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import { useDownloadStore } from "@/stores/download-store";
import { toast } from "@/stores/toast-store";
import type {
  ConflictCheckResult,
  CorrelateResult,
  DownloadJobOut,
  DownloadRequest,
  DownloadStartResult,
  Game,
  GameCreate,
  InstallRequest,
  InstallResult,
  NexusKeyResult,
  NexusSyncResult,
  OnboardingStatus,
  PathValidation,
  ProfileExport,
  ProfileOut,
  ScanResult,
  Setting,
  ToggleResult,
  UninstallResult,
  UpdateCheckResult,
} from "@/types/api";

export function useCreateGame() {
  const qc = useQueryClient();
  return useMutation<Game, Error, GameCreate>({
    mutationFn: (data) => api.post("/api/v1/games/", data),
    onSuccess: (game) => {
      qc.invalidateQueries({ queryKey: ["games"] });
      toast.success("Game added", game.name);
    },
    onError: () => toast.error("Failed to add game"),
  });
}

export function useDeleteGame() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (name) => api.delete(`/api/v1/games/${name}`),
    onSuccess: (_, name) => {
      qc.invalidateQueries({ queryKey: ["games"] });
      toast.success("Game deleted", name);
    },
    onError: () => toast.error("Failed to delete game"),
  });
}

export function useValidateNexusKey() {
  return useMutation<NexusKeyResult, Error, string>({
    mutationFn: (apiKey) =>
      api.post("/api/v1/nexus/validate", { api_key: apiKey }),
  });
}

export function useConnectNexus() {
  return useMutation<NexusKeyResult, Error, string>({
    mutationFn: (apiKey) =>
      api.post("/api/v1/nexus/connect", { api_key: apiKey }),
  });
}

export function useSyncNexus() {
  const qc = useQueryClient();
  return useMutation<NexusSyncResult, Error, string>({
    mutationFn: (gameName) =>
      api.post(`/api/v1/nexus/sync-history/${gameName}`),
    onSuccess: (_, gameName) => {
      qc.invalidateQueries({ queryKey: ["nexus-downloads", gameName] });
    },
  });
}

export function useScanMods() {
  const qc = useQueryClient();
  return useMutation<ScanResult, Error, string>({
    mutationFn: (gameName) =>
      api.post(`/api/v1/games/${gameName}/mods/scan`),
    onSuccess: (_, gameName) => {
      qc.invalidateQueries({ queryKey: ["mods", gameName] });
    },
  });
}

export function useCorrelate() {
  const qc = useQueryClient();
  return useMutation<CorrelateResult, Error, string>({
    mutationFn: (gameName) =>
      api.post(`/api/v1/games/${gameName}/mods/correlate`),
    onSuccess: (_, gameName) => {
      qc.invalidateQueries({ queryKey: ["mods", gameName] });
    },
  });
}

export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation<Setting[], Error, Record<string, string>>({
    mutationFn: (settings) =>
      api.put("/api/v1/settings/", { settings }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast.success("Settings saved");
    },
    onError: () => toast.error("Failed to save settings"),
  });
}

export function useCompleteOnboarding() {
  const qc = useQueryClient();
  return useMutation<OnboardingStatus, Error, { openai_api_key?: string; nexus_api_key?: string }>({
    mutationFn: (data) => api.post("/api/v1/onboarding/complete", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding"] }),
  });
}

export function useInstallMod() {
  const qc = useQueryClient();
  return useMutation<InstallResult, Error, { gameName: string; data: InstallRequest }>({
    mutationFn: ({ gameName, data }) =>
      api.post(`/api/v1/games/${gameName}/install/`, data),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      qc.invalidateQueries({ queryKey: ["available-archives", gameName] });
      toast.success("Mod installed");
    },
    onError: () => toast.error("Installation failed"),
  });
}

export function useUninstallMod() {
  const qc = useQueryClient();
  return useMutation<UninstallResult, Error, { gameName: string; modId: number }>({
    mutationFn: ({ gameName, modId }) =>
      api.delete(`/api/v1/games/${gameName}/install/installed/${modId}`),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      toast.success("Mod uninstalled");
    },
    onError: () => toast.error("Failed to uninstall mod"),
  });
}

export function useToggleMod() {
  const qc = useQueryClient();
  return useMutation<ToggleResult, Error, { gameName: string; modId: number }>({
    mutationFn: ({ gameName, modId }) =>
      api.patch(`/api/v1/games/${gameName}/install/installed/${modId}/toggle`),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
    },
    onError: () => toast.error("Failed to toggle mod"),
  });
}

export function useCheckConflicts() {
  return useMutation<ConflictCheckResult, Error, { gameName: string; archiveFilename: string }>({
    mutationFn: ({ gameName, archiveFilename }) =>
      api.get(
        `/api/v1/games/${gameName}/install/conflicts?archive_filename=${encodeURIComponent(archiveFilename)}`,
      ),
  });
}

export function useSaveProfile() {
  const qc = useQueryClient();
  return useMutation<ProfileOut, Error, { gameName: string; name: string }>({
    mutationFn: ({ gameName, name }) =>
      api.post(`/api/v1/games/${gameName}/profiles/`, { name }),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["profiles", gameName] });
      toast.success("Profile created");
    },
    onError: () => toast.error("Failed to create profile"),
  });
}

export function useLoadProfile() {
  const qc = useQueryClient();
  return useMutation<ProfileOut, Error, { gameName: string; profileId: number }>({
    mutationFn: ({ gameName, profileId }) =>
      api.post(`/api/v1/games/${gameName}/profiles/${profileId}/load`),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      qc.invalidateQueries({ queryKey: ["profiles", gameName] });
    },
  });
}

export function useDeleteProfile() {
  const qc = useQueryClient();
  return useMutation<void, Error, { gameName: string; profileId: number }>({
    mutationFn: ({ gameName, profileId }) =>
      api.delete(`/api/v1/games/${gameName}/profiles/${profileId}`),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["profiles", gameName] });
      toast.success("Profile deleted");
    },
    onError: () => toast.error("Failed to delete profile"),
  });
}

export function useExportProfile() {
  return useMutation<ProfileExport, Error, { gameName: string; profileId: number }>({
    mutationFn: ({ gameName, profileId }) =>
      api.post(`/api/v1/games/${gameName}/profiles/${profileId}/export`),
  });
}

export function useImportProfile() {
  const qc = useQueryClient();
  return useMutation<ProfileOut, Error, { gameName: string; data: ProfileExport }>({
    mutationFn: ({ gameName, data }) =>
      api.post(`/api/v1/games/${gameName}/profiles/import`, data),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["profiles", gameName] });
    },
  });
}

export function useCheckUpdates() {
  const qc = useQueryClient();
  return useMutation<UpdateCheckResult, Error, string>({
    mutationFn: (gameName) =>
      api.post(`/api/v1/games/${gameName}/updates/check`),
    onSuccess: (data, gameName) => {
      qc.setQueryData(["updates", gameName], data);
      toast.success(
        "Update check complete",
        `${data.updates_available} update${data.updates_available === 1 ? "" : "s"} found`,
      );
    },
    onError: () => toast.error("Update check failed"),
  });
}

export function useStartDownload() {
  const qc = useQueryClient();
  return useMutation<DownloadStartResult, Error, { gameName: string; data: DownloadRequest }>({
    mutationFn: ({ gameName, data }) =>
      api.post(`/api/v1/games/${gameName}/downloads/`, data),
    onSuccess: (result, { gameName }) => {
      if (result.requires_nxm) {
        toast.warning("Premium required", "Open the mod on Nexus to download manually");
      } else {
        useDownloadStore.getState().setJob(result.job);
        toast.info("Download started", result.job.file_name);
      }
      qc.invalidateQueries({ queryKey: ["download-jobs", gameName] });
    },
    onError: () => toast.error("Download failed"),
  });
}

export function useStartModDownload() {
  const qc = useQueryClient();
  return useMutation<DownloadStartResult, Error, { gameName: string; nexusModId: number }>({
    mutationFn: ({ gameName, nexusModId }) =>
      api.post(`/api/v1/games/${gameName}/downloads/from-mod`, { nexus_mod_id: nexusModId }),
    onSuccess: (result, { gameName }) => {
      if (result.requires_nxm) {
        toast.warning("Premium required", "Open the mod on Nexus to download manually");
      } else {
        useDownloadStore.getState().setJob(result.job);
        toast.info("Download started", result.job.file_name);
      }
      qc.invalidateQueries({ queryKey: ["download-jobs", gameName] });
    },
    onError: () => toast.error("Download failed"),
  });
}

export function useCancelDownload() {
  const qc = useQueryClient();
  return useMutation<DownloadJobOut, Error, { gameName: string; jobId: number }>({
    mutationFn: ({ gameName, jobId }) =>
      api.post(`/api/v1/games/${gameName}/downloads/${jobId}/cancel`),
    onSuccess: (_, { gameName }) => {
      toast.info("Download cancelled");
      qc.invalidateQueries({ queryKey: ["download-jobs", gameName] });
    },
    onError: () => toast.error("Failed to cancel download"),
  });
}

export function useValidatePath() {
  return useMutation<PathValidation, Error, { install_path: string; domain_name?: string }>({
    mutationFn: (data) =>
      api.post("/api/v1/games/validate-path", data),
  });
}
