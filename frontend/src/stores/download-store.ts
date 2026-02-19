import { create } from "zustand";

import type { DownloadJobOut, DownloadStatus } from "@/types/api";

interface DownloadProgress {
  job_id: number;
  status: DownloadStatus;
  progress_bytes: number;
  total_bytes: number;
  percent: number;
  file_name?: string;
  error?: string;
}

interface DownloadState {
  jobs: Record<number, DownloadJobOut>;
  activeGame: string | null;
  eventSource: EventSource | null;
  updateJob: (update: DownloadProgress) => void;
  setJob: (job: DownloadJobOut) => void;
  clearCompleted: () => void;
  reset: () => void;
}

export const useDownloadStore = create<DownloadState>((set) => ({
  jobs: {},
  activeGame: null,
  eventSource: null,

  updateJob: (update) =>
    set((state) => {
      const existing = state.jobs[update.job_id];
      if (!existing) return state;
      return {
        jobs: {
          ...state.jobs,
          [update.job_id]: {
            ...existing,
            status: update.status,
            progress_bytes: update.progress_bytes,
            total_bytes: update.total_bytes,
            percent: update.percent,
            file_name: update.file_name ?? existing.file_name,
            error: update.error ?? existing.error,
          },
        },
      };
    }),

  setJob: (job) =>
    set((state) => ({
      jobs: { ...state.jobs, [job.id]: job },
    })),

  clearCompleted: () =>
    set((state) => {
      const filtered: Record<number, DownloadJobOut> = {};
      for (const [id, job] of Object.entries(state.jobs)) {
        if (job.status !== "completed" && job.status !== "failed" && job.status !== "cancelled") {
          filtered[Number(id)] = job;
        }
      }
      return { jobs: filtered };
    }),

  reset: () => set({ jobs: {}, activeGame: null, eventSource: null }),
}));
