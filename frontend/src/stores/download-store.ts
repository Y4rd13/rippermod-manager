import { create } from "zustand";

import type { DownloadJobOut } from "@/types/api";

interface DownloadState {
  jobs: Record<number, DownloadJobOut>;
  setJob: (job: DownloadJobOut) => void;
  clearCompleted: () => void;
  reset: () => void;
}

export const useDownloadStore = create<DownloadState>((set) => ({
  jobs: {},

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

  reset: () => set({ jobs: {} }),
}));
