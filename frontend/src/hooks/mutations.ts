import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import type {
  CorrelateResult,
  GameCreate,
  Game,
  NexusKeyResult,
  NexusSyncResult,
  OnboardingStatus,
  ScanResult,
  Setting,
} from "@/types/api";

export function useCreateGame() {
  const qc = useQueryClient();
  return useMutation<Game, Error, GameCreate>({
    mutationFn: (data) => api.post("/api/v1/games", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["games"] }),
  });
}

export function useDeleteGame() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (name) => api.delete(`/api/v1/games/${name}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["games"] }),
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
      api.put("/api/v1/settings", { settings }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
}

export function useCompleteOnboarding() {
  const qc = useQueryClient();
  return useMutation<OnboardingStatus, Error, { openai_api_key?: string; nexus_api_key?: string }>({
    mutationFn: (data) => api.post("/api/v1/onboarding/complete", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding"] }),
  });
}
