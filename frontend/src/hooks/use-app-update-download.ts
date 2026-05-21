import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api-client";

export type AppUpdateDownloadState = "idle" | "downloading" | "ready" | "error";

export interface AppUpdateDownloadStatus {
  state: AppUpdateDownloadState;
  version: string | null;
  file_name: string | null;
  downloaded_bytes: number;
  total_bytes: number;
  path: string | null;
  error_code: string | null;
  error_message: string | null;
}

const QUERY_KEY = ["app-update", "download"] as const;

/**
 * Polls the backend self-update download status. Polls every 1s while a
 * download is in progress so the UI can show a progress bar; otherwise
 * idles to avoid hammering the loopback.
 */
export function useAppUpdateDownloadStatus() {
  return useQuery<AppUpdateDownloadStatus>({
    queryKey: QUERY_KEY,
    queryFn: () => api.get("/api/v1/app-update/download"),
    refetchInterval: (query) =>
      query.state.data?.state === "downloading" ? 1000 : false,
    staleTime: 0,
  });
}

export function useStartAppUpdateDownload() {
  const qc = useQueryClient();
  return useMutation<AppUpdateDownloadStatus>({
    mutationFn: () => api.post("/api/v1/app-update/download"),
    onSuccess: (data) => qc.setQueryData(QUERY_KEY, data),
  });
}

export function useCancelAppUpdateDownload() {
  const qc = useQueryClient();
  return useMutation<AppUpdateDownloadStatus>({
    mutationFn: () => api.post("/api/v1/app-update/download/cancel"),
    onSuccess: (data) => qc.setQueryData(QUERY_KEY, data),
  });
}
