import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import { formatBytes } from "@/lib/format";
import { useDownloadStore } from "@/stores/download-store";
import { toast } from "@/stores/toast-store";
import type {
  ArchiveDeleteResult,
  ConflictCheckResult,
  CorrelateResult,
  PreferModRequest,
  PreferModResult,
  ReindexResult,
  CorrelationBrief,
  DownloadJobOut,
  DownloadRequest,
  DownloadStartResult,
  Game,
  GameCreate,
  InstallRequest,
  InstallResult,
  ModActionResult,
  NexusLinkResult,
  NexusSyncResult,
  OnboardingStatus,
  OrphanCleanupResult,
  PathValidation,
  ProfileCompareOut,
  ProfileCompareRequest,
  ProfileDiffOut,
  ProfileExport,
  ProfileImportResult,
  ProfileLoadResult,
  ProfileOut,
  ProfileUpdate,
  ResolveResult,
  ScanResult,
  Setting,
  ToggleResult,
  TrendingResult,
  UninstallResult,
  UpdateCheckResult,
} from "@/types/api";
import type {
  FomodConfigOut,
  FomodInstallRequest,
  FomodPreviewRequest,
  FomodPreviewResult,
} from "@/types/fomod";

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
  return useMutation<OnboardingStatus, Error, { openai_api_key?: string }>({
    mutationFn: (data) => api.post("/api/v1/onboarding/complete", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding"] }),
  });
}

export function useDisconnectNexus() {
  const qc = useQueryClient();
  return useMutation<OnboardingStatus, Error, void>({
    mutationFn: () => api.post("/api/v1/onboarding/reset"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["onboarding"] });
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast.success("Nexus account disconnected");
    },
    onError: () => toast.error("Failed to disconnect"),
  });
}

export function useInstallMod() {
  const qc = useQueryClient();
  return useMutation<InstallResult, Error, { gameName: string; data: InstallRequest }>({
    mutationFn: ({ gameName, data }) =>
      api.post(`/api/v1/games/${gameName}/install/`, data),
    onSuccess: (result, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      qc.invalidateQueries({ queryKey: ["available-archives", gameName] });
      toast.success("Mod installed", `${result.files_extracted} files extracted`);
      if (result.files_overwritten > 0) {
        toast.warning(
          "Files overwritten",
          `${result.files_overwritten} existing file${result.files_overwritten === 1 ? " was" : "s were"} replaced`,
        );
      }
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
      qc.invalidateQueries({ queryKey: ["available-archives", gameName] });
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

export function useDeleteArchive() {
  const qc = useQueryClient();
  return useMutation<ArchiveDeleteResult, Error, { gameName: string; filename: string }>({
    mutationFn: ({ gameName, filename }) =>
      api.delete(`/api/v1/games/${gameName}/install/archives/${encodeURIComponent(filename)}`),
    onSuccess: (result, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["available-archives", gameName] });
      if (result.deleted) {
        toast.success("Archive deleted", result.filename);
      } else {
        toast.error("Could not delete archive", result.message);
      }
    },
    onError: () => toast.error("Failed to delete archive"),
  });
}

export function useCleanupOrphans() {
  const qc = useQueryClient();
  return useMutation<OrphanCleanupResult, Error, string>({
    mutationFn: (gameName) =>
      api.post(`/api/v1/games/${gameName}/install/archives/cleanup-orphans`),
    onSuccess: (result, gameName) => {
      qc.invalidateQueries({ queryKey: ["available-archives", gameName] });
      if (result.deleted_count > 0) {
        const freed = formatBytes(result.freed_bytes);
        toast.success(
          "Orphan archives cleaned",
          `${result.deleted_count} file${result.deleted_count === 1 ? "" : "s"} removed, ${freed} freed`,
        );
      } else {
        toast.info("No orphan archives found");
      }
    },
    onError: () => toast.error("Failed to clean orphan archives"),
  });
}

export function useLinkArchiveToNexus() {
  const qc = useQueryClient();
  return useMutation<NexusLinkResult, Error, { gameName: string; filename: string; nexusModId: number }>({
    mutationFn: ({ gameName, filename, nexusModId }) =>
      api.put(
        `/api/v1/games/${gameName}/install/archives/${encodeURIComponent(filename)}/nexus-link`,
        { nexus_mod_id: nexusModId },
      ),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["available-archives", gameName] });
      toast.success("Archive linked to Nexus");
    },
    onError: () => toast.error("Failed to link archive"),
  });
}

export function useUnlinkArchiveFromNexus() {
  const qc = useQueryClient();
  return useMutation<void, Error, { gameName: string; filename: string }>({
    mutationFn: ({ gameName, filename }) =>
      api.delete(
        `/api/v1/games/${gameName}/install/archives/${encodeURIComponent(filename)}/nexus-link`,
      ),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["available-archives", gameName] });
      toast.success("Nexus link removed");
    },
    onError: () => toast.error("Failed to unlink archive"),
  });
}

export function useSaveProfile() {
  const qc = useQueryClient();
  return useMutation<
    ProfileOut,
    Error,
    { gameName: string; name: string; description?: string }
  >({
    mutationFn: ({ gameName, name, description }) =>
      api.post(`/api/v1/games/${gameName}/profiles/`, { name, description }),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["profiles", gameName] });
      toast.success("Profile created");
    },
    onError: () => toast.error("Failed to create profile"),
  });
}

export function useLoadProfile() {
  const qc = useQueryClient();
  return useMutation<ProfileLoadResult, Error, { gameName: string; profileId: number }>({
    mutationFn: ({ gameName, profileId }) =>
      api.post(`/api/v1/games/${gameName}/profiles/${profileId}/load`),
    onSuccess: (result, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      qc.invalidateQueries({ queryKey: ["profiles", gameName] });
      if (result.skipped_count > 0) {
        toast.warning(
          "Some mods were skipped",
          `${result.skipped_count} mod${result.skipped_count === 1 ? " is" : "s are"} no longer installed`,
        );
      } else {
        toast.success("Profile loaded");
      }
    },
    onError: () => toast.error("Failed to load profile"),
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
  return useMutation<ProfileImportResult, Error, { gameName: string; data: ProfileExport }>({
    mutationFn: ({ gameName, data }) =>
      api.post(`/api/v1/games/${gameName}/profiles/import`, data),
    onSuccess: (result, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["profiles", gameName] });
      if (result.skipped_count > 0) {
        toast.warning(
          "Profile imported",
          `${result.matched_count} matched, ${result.skipped_count} skipped`,
        );
      } else {
        toast.success("Profile imported", `${result.matched_count} mods matched`);
      }
    },
    onError: () => toast.error("Failed to import profile"),
  });
}

export function usePreviewProfile() {
  return useMutation<ProfileDiffOut, Error, { gameName: string; profileId: number }>({
    mutationFn: ({ gameName, profileId }) =>
      api.post(`/api/v1/games/${gameName}/profiles/${profileId}/preview`),
  });
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation<ProfileOut, Error, { gameName: string; profileId: number; data: ProfileUpdate }>({
    mutationFn: ({ gameName, profileId, data }) =>
      api.patch(`/api/v1/games/${gameName}/profiles/${profileId}`, data),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["profiles", gameName] });
      toast.success("Profile updated");
    },
    onError: () => toast.error("Failed to update profile"),
  });
}

export function useDuplicateProfile() {
  const qc = useQueryClient();
  return useMutation<ProfileOut, Error, { gameName: string; profileId: number; name: string }>({
    mutationFn: ({ gameName, profileId, name }) =>
      api.post(`/api/v1/games/${gameName}/profiles/${profileId}/duplicate`, { name }),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["profiles", gameName] });
      toast.success("Profile duplicated");
    },
    onError: () => toast.error("Failed to duplicate profile"),
  });
}

export function useCompareProfiles() {
  return useMutation<ProfileCompareOut, Error, { gameName: string; data: ProfileCompareRequest }>({
    mutationFn: ({ gameName, data }) =>
      api.post(`/api/v1/games/${gameName}/profiles/compare`, data),
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
        return;
      }
      if (result.job) {
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
      if (result.requires_file_selection) {
        return;
      }
      if (result.requires_nxm) {
        toast.warning("Premium required", "Open the mod on Nexus to download manually");
        return;
      }
      if (result.job) {
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

export function useRefreshTrending() {
  const qc = useQueryClient();
  return useMutation<TrendingResult, Error, string>({
    mutationFn: (gameName) =>
      api.get(`/api/v1/games/${gameName}/trending/?refresh=true`),
    onSuccess: (data, gameName) => {
      qc.setQueryData(["trending", gameName], data);
      toast.success("Trending mods refreshed");
    },
    onError: () => toast.error("Failed to refresh trending mods"),
  });
}

export function useConfirmCorrelation() {
  const qc = useQueryClient();
  return useMutation<CorrelationBrief, Error, { gameName: string; modGroupId: number }>({
    mutationFn: ({ gameName, modGroupId }) =>
      api.patch(`/api/v1/games/${gameName}/mods/${modGroupId}/correlation/confirm`),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["mods", gameName] });
      toast.success("Match confirmed");
    },
    onError: () => toast.error("Failed to confirm match"),
  });
}

export function useRejectCorrelation() {
  const qc = useQueryClient();
  return useMutation<{ deleted: boolean }, Error, { gameName: string; modGroupId: number }>({
    mutationFn: ({ gameName, modGroupId }) =>
      api.delete(`/api/v1/games/${gameName}/mods/${modGroupId}/correlation`),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["mods", gameName] });
      toast.success("Match rejected");
    },
    onError: () => toast.error("Failed to reject match"),
  });
}

export function useReassignCorrelation() {
  const qc = useQueryClient();
  return useMutation<
    CorrelationBrief,
    Error,
    { gameName: string; modGroupId: number; nexusModId: number }
  >({
    mutationFn: ({ gameName, modGroupId, nexusModId }) =>
      api.put(`/api/v1/games/${gameName}/mods/${modGroupId}/correlation`, {
        nexus_mod_id: nexusModId,
      }),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["mods", gameName] });
      toast.success("Match reassigned");
    },
    onError: () => toast.error("Failed to reassign match"),
  });
}

export function useResolveConflict() {
  const qc = useQueryClient();
  return useMutation<ResolveResult, Error, { gameName: string; modId: number }>({
    mutationFn: ({ gameName, modId }) =>
      api.post(`/api/v1/games/${gameName}/conflicts/inbox/${modId}/resolve`, { action: "reinstall" }),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["conflicts", gameName] });
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      toast.success("Conflict resolved", "Mod reinstalled to reclaim files");
    },
    onError: () => toast.error("Failed to resolve conflict"),
  });
}

export function useReindexConflicts() {
  const qc = useQueryClient();
  return useMutation<ReindexResult, Error, string>({
    mutationFn: (gameName) =>
      api.post(`/api/v1/games/${gameName}/conflicts/reindex`),
    onSuccess: (result, gameName) => {
      qc.invalidateQueries({ queryKey: ["conflicts", gameName] });
      qc.invalidateQueries({ queryKey: ["conflict-summary", gameName] });
      qc.invalidateQueries({ queryKey: ["conflict-graph", gameName] });
      qc.invalidateQueries({ queryKey: ["archive-conflict-summaries", gameName] });
      toast.success(
        "Reindex complete",
        `${result.conflicts_found} conflict${result.conflicts_found === 1 ? "" : "s"} found in ${result.duration_ms}ms`,
      );
    },
    onError: () => toast.error("Reindex failed"),
  });
}

export function usePreferModPreview() {
  return useMutation<PreferModResult, Error, { gameName: string; data: PreferModRequest }>({
    mutationFn: ({ gameName, data }) =>
      api.post(`/api/v1/games/${gameName}/load-order/prefer/preview`, data),
  });
}

export function usePreferMod() {
  const qc = useQueryClient();
  return useMutation<PreferModResult, Error, { gameName: string; data: PreferModRequest }>({
    mutationFn: ({ gameName, data }) =>
      api.post(`/api/v1/games/${gameName}/load-order/prefer`, data),
    onSuccess: (result, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["archive-conflict-summaries", gameName] });
      qc.invalidateQueries({ queryKey: ["conflict-summary", gameName] });
      qc.invalidateQueries({ queryKey: ["conflict-graph", gameName] });
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      toast.success(
        "Load order updated",
        `${result.renames.length} archive${result.renames.length === 1 ? "" : "s"} renamed`,
      );
    },
    onError: () => toast.error("Failed to apply load order preference"),
  });
}

export function useFomodConfig() {
  return useMutation<FomodConfigOut, Error, { gameName: string; archiveFilename: string }>({
    mutationFn: ({ gameName, archiveFilename }) =>
      api.get(
        `/api/v1/games/${gameName}/install/fomod/config?archive_filename=${encodeURIComponent(archiveFilename)}`,
      ),
  });
}

export function useFomodInstall() {
  const qc = useQueryClient();
  return useMutation<InstallResult, Error, { gameName: string; data: FomodInstallRequest }>({
    mutationFn: ({ gameName, data }) =>
      api.post(`/api/v1/games/${gameName}/install/fomod/install`, data),
    onSuccess: (result, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      qc.invalidateQueries({ queryKey: ["available-archives", gameName] });
      toast.success("Mod installed", `${result.files_extracted} files extracted`);
      if (result.files_overwritten > 0) {
        toast.warning(
          "Files overwritten",
          `${result.files_overwritten} existing file${result.files_overwritten === 1 ? " was" : "s were"} replaced`,
        );
      }
    },
    onError: () => toast.error("FOMOD installation failed"),
  });
}

export function useFomodPreview() {
  return useMutation<FomodPreviewResult, Error, { gameName: string; data: FomodPreviewRequest }>({
    mutationFn: ({ gameName, data }) =>
      api.post(`/api/v1/games/${gameName}/install/fomod/preview`, data),
  });
}

export function useEndorseMod() {
  const qc = useQueryClient();
  return useMutation<ModActionResult, Error, { gameName: string; modId: number }>({
    mutationFn: ({ gameName, modId }) =>
      api.post(`/api/v1/nexus/${gameName}/mods/${modId}/endorse`),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["trending", gameName] });
      qc.invalidateQueries({ queryKey: ["nexus-downloads", gameName] });
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      qc.invalidateQueries({ queryKey: ["mod-detail"] });
      toast.success("Mod endorsed");
    },
    onError: () => toast.error("Failed to endorse mod"),
  });
}

export function useAbstainMod() {
  const qc = useQueryClient();
  return useMutation<ModActionResult, Error, { gameName: string; modId: number }>({
    mutationFn: ({ gameName, modId }) =>
      api.post(`/api/v1/nexus/${gameName}/mods/${modId}/abstain`),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["trending", gameName] });
      qc.invalidateQueries({ queryKey: ["nexus-downloads", gameName] });
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      qc.invalidateQueries({ queryKey: ["mod-detail"] });
      toast.success("Endorsement removed");
    },
    onError: () => toast.error("Failed to remove endorsement"),
  });
}

export function useTrackMod() {
  const qc = useQueryClient();
  return useMutation<ModActionResult, Error, { gameName: string; modId: number }>({
    mutationFn: ({ gameName, modId }) =>
      api.post(`/api/v1/nexus/${gameName}/mods/${modId}/track`),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["trending", gameName] });
      qc.invalidateQueries({ queryKey: ["nexus-downloads", gameName] });
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      qc.invalidateQueries({ queryKey: ["mod-detail"] });
      toast.success("Mod tracked");
    },
    onError: () => toast.error("Failed to track mod"),
  });
}

export function useUntrackMod() {
  const qc = useQueryClient();
  return useMutation<ModActionResult, Error, { gameName: string; modId: number }>({
    mutationFn: ({ gameName, modId }) =>
      api.delete(`/api/v1/nexus/${gameName}/mods/${modId}/track`),
    onSuccess: (_, { gameName }) => {
      qc.invalidateQueries({ queryKey: ["trending", gameName] });
      qc.invalidateQueries({ queryKey: ["nexus-downloads", gameName] });
      qc.invalidateQueries({ queryKey: ["installed-mods", gameName] });
      qc.invalidateQueries({ queryKey: ["mod-detail"] });
      toast.success("Mod untracked");
    },
    onError: () => toast.error("Failed to untrack mod"),
  });
}
