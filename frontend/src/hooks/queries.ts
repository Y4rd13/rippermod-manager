import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import type {
  AvailableArchive,
  DownloadJobOut,
  Game,
  GameVersion,
  InstalledModOut,
  ModGroup,
  NexusDownload,
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

export function useTrendingMods(gameName: string) {
  return useQuery<TrendingResult>({
    queryKey: ["trending", gameName],
    queryFn: () => api.get(`/api/v1/games/${gameName}/trending/`),
    enabled: !!gameName,
    staleTime: 15 * 60 * 1000,
  });
}
