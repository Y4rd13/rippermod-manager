import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import type {
  ArchiveConflictSummariesResult,
  ArchiveContentsResult,
  ArchivePreviewResult,
  AvailableArchive,
  ConflictGraphResult,
  ConflictKind,
  ConflictsOverview,
  ConflictSummaryResult,
  DownloadJobOut,
  Game,
  GameVersion,
  InstalledModOut,
  ModConflictDetail,
  ModDetail,
  ModGroup,
  NexusDownload,
  NexusDownloadBrief,
  OnboardingStatus,
  ProfileOut,
  Setting,
  TrendingResult,
  UpdateCheckResult,
} from "@/types/api";

export function useOnboardingStatus() {
  return useQuery<OnboardingStatus>({
    queryKey: ["onboarding", "status"],
    queryFn: () => api.get("/api/v1/onboarding/status"),
  });
}

export function useGames() {
  return useQuery<Game[]>({
    queryKey: ["games"],
    queryFn: () => api.get("/api/v1/games/"),
  });
}

export function useGame(name: string) {
  return useQuery<Game>({
    queryKey: ["games", name],
    queryFn: () => api.get(`/api/v1/games/${name}`),
    enabled: !!name,
  });
}

export function useGameVersion(gameName: string) {
  return useQuery<GameVersion>({
    queryKey: ["game-version", gameName],
    queryFn: () => api.get(`/api/v1/games/${gameName}/version`),
    enabled: !!gameName,
    staleTime: 5 * 60 * 1000,
  });
}

export function useMods(gameName: string) {
  return useQuery<ModGroup[]>({
    queryKey: ["mods", gameName],
    queryFn: () => api.get(`/api/v1/games/${gameName}/mods/`),
    enabled: !!gameName,
  });
}

export function useNexusDownloads(gameName: string) {
  return useQuery<NexusDownload[]>({
    queryKey: ["nexus-downloads", gameName],
    queryFn: () => api.get(`/api/v1/nexus/downloads/${gameName}`),
    enabled: !!gameName,
  });
}

export function useEndorsedMods(gameName: string) {
  return useQuery<NexusDownload[]>({
    queryKey: ["nexus-downloads", gameName, "endorsed"],
    queryFn: () => api.get(`/api/v1/nexus/downloads/${gameName}?source=endorsed`),
    enabled: !!gameName,
  });
}

export function useTrackedMods(gameName: string) {
  return useQuery<NexusDownload[]>({
    queryKey: ["nexus-downloads", gameName, "tracked"],
    queryFn: () => api.get(`/api/v1/nexus/downloads/${gameName}?source=tracked`),
    enabled: !!gameName,
  });
}

export function useUpdates(gameName: string) {
  return useQuery<UpdateCheckResult>({
    queryKey: ["updates", gameName],
    queryFn: () => api.get(`/api/v1/games/${gameName}/updates/`),
    enabled: !!gameName,
  });
}

export function useSettings() {
  return useQuery<Setting[]>({
    queryKey: ["settings"],
    queryFn: () => api.get("/api/v1/settings/"),
  });
}

export function useHasOpenaiKey(): boolean {
  const { data: settings = [] } = useSettings();
  return settings.some((s) => s.key === "openai_api_key" && s.value);
}

export function useArchiveContents(gameName: string, filename: string | null) {
  return useQuery<ArchiveContentsResult>({
    queryKey: ["archive-contents", gameName, filename],
    queryFn: () =>
      api.get(
        `/api/v1/games/${gameName}/install/archives/${encodeURIComponent(filename!)}/contents`,
      ),
    enabled: !!gameName && !!filename,
  });
}

export function useAvailableArchives(gameName: string) {
  return useQuery<AvailableArchive[]>({
    queryKey: ["available-archives", gameName],
    queryFn: () =>
      api.get(`/api/v1/games/${gameName}/install/available`),
    enabled: !!gameName,
  });
}

export function useInstalledMods(gameName: string) {
  return useQuery<InstalledModOut[]>({
    queryKey: ["installed-mods", gameName],
    queryFn: () =>
      api.get(`/api/v1/games/${gameName}/install/installed`),
    enabled: !!gameName,
  });
}

export function useProfiles(gameName: string) {
  return useQuery<ProfileOut[]>({
    queryKey: ["profiles", gameName],
    queryFn: () => api.get(`/api/v1/games/${gameName}/profiles/`),
    enabled: !!gameName,
  });
}

export function useDownloadJobs(gameName: string) {
  return useQuery<DownloadJobOut[]>({
    queryKey: ["download-jobs", gameName],
    queryFn: () => api.get(`/api/v1/games/${gameName}/downloads/`),
    enabled: !!gameName,
    refetchInterval: 5000,
  });
}

export function useModDetail(gameDomain: string, modId: number | null) {
  return useQuery<ModDetail>({
    queryKey: ["mod-detail", gameDomain, modId],
    queryFn: () => api.get(`/api/v1/nexus/mods/${gameDomain}/${modId}/detail`),
    enabled: !!gameDomain && modId != null,
    staleTime: 10 * 60 * 1000,
  });
}

export function useTrendingMods(gameName: string) {
  return useQuery<TrendingResult>({
    queryKey: ["trending", gameName],
    queryFn: () => api.get(`/api/v1/games/${gameName}/trending/`),
    enabled: !!gameName,
    staleTime: 15 * 60 * 1000,
  });
}

export function useConflictsOverview(gameName: string) {
  return useQuery<ConflictsOverview>({
    queryKey: ["conflicts", gameName],
    queryFn: () => api.get(`/api/v1/games/${gameName}/conflicts/inbox`),
    enabled: !!gameName,
    staleTime: 60_000,
  });
}

export function useModConflicts(gameName: string, modId: number | null) {
  return useQuery<ModConflictDetail>({
    queryKey: ["conflicts", gameName, modId],
    queryFn: () => api.get(`/api/v1/games/${gameName}/conflicts/inbox/${modId}`),
    enabled: !!gameName && modId != null,
  });
}

export function useSearchNexusDownloads(gameName: string, query: string) {
  return useQuery<NexusDownloadBrief[]>({
    queryKey: ["nexus-search", gameName, query],
    queryFn: () =>
      api.get(`/api/v1/nexus/downloads/${gameName}/search?q=${encodeURIComponent(query)}`),
    enabled: !!gameName && query.length >= 2,
  });
}

export function useArchivePreview(gameName: string, archiveFilename: string | null) {
  return useQuery<ArchivePreviewResult>({
    queryKey: ["archive-preview", gameName, archiveFilename],
    queryFn: () =>
      api.get(
        `/api/v1/games/${gameName}/install/preview?archive_filename=${encodeURIComponent(archiveFilename!)}`,
      ),
    enabled: !!gameName && !!archiveFilename,
  });
}

export function useFileContentsPreview(url: string | null) {
  return useQuery<ArchiveContentsResult>({
    queryKey: ["file-contents-preview", url],
    queryFn: () =>
      api.get(`/api/v1/nexus/file-contents-preview?url=${encodeURIComponent(url!)}`),
    enabled: !!url,
    staleTime: 30 * 60 * 1000,
  });
}

export function useArchiveConflictSummaries(gameName: string) {
  return useQuery<ArchiveConflictSummariesResult>({
    queryKey: ["archive-conflict-summaries", gameName],
    queryFn: () => api.get(`/api/v1/games/${gameName}/conflicts/archive-summaries`),
    enabled: !!gameName,
    staleTime: 60_000,
  });
}

export function useConflictSummary(gameName: string, kind?: ConflictKind) {
  const params = kind ? `?kind=${kind}` : "";
  return useQuery<ConflictSummaryResult>({
    queryKey: ["conflict-summary", gameName, kind],
    queryFn: () => api.get(`/api/v1/games/${gameName}/conflicts/summary${params}`),
    enabled: !!gameName,
    staleTime: 60_000,
  });
}

export function useConflictGraph(gameName: string, enabled = true) {
  return useQuery<ConflictGraphResult>({
    queryKey: ["conflict-graph", gameName],
    queryFn: () => api.get(`/api/v1/games/${gameName}/conflicts/graph`),
    enabled: !!gameName && enabled,
    staleTime: 60_000,
  });
}
