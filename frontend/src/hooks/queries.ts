import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import type {
  Game,
  ModGroup,
  NexusDownload,
  OnboardingStatus,
  Setting,
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
    queryFn: () => api.get("/api/v1/games"),
  });
}

export function useGame(name: string) {
  return useQuery<Game>({
    queryKey: ["games", name],
    queryFn: () => api.get(`/api/v1/games/${name}`),
    enabled: !!name,
  });
}

export function useMods(gameName: string) {
  return useQuery<ModGroup[]>({
    queryKey: ["mods", gameName],
    queryFn: () => api.get(`/api/v1/games/${gameName}/mods`),
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

export function useUpdates(gameName: string) {
  return useQuery<UpdateCheckResult>({
    queryKey: ["updates", gameName],
    queryFn: () => api.get(`/api/v1/games/${gameName}/updates`),
    enabled: !!gameName,
  });
}

export function useSettings() {
  return useQuery<Setting[]>({
    queryKey: ["settings"],
    queryFn: () => api.get("/api/v1/settings"),
  });
}
