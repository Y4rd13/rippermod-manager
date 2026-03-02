import { create } from "zustand";

import type { DownloadJobOut } from "@/types/api";

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

interface DownloadState {
  jobs: Record<number, DownloadJobOut>;
  footerExpanded: boolean;
  setJob: (job: DownloadJobOut) => void;
  syncJobs: (polled: DownloadJobOut[]) => void;
  toggleFooter: () => void;
  clearCompleted: () => void;
  reset: () => void;
}

export const useDownloadStore = create<DownloadState>((set) => ({
  jobs: {},
  footerExpanded: false,

  setJob: (job) =>
    set((state) => ({
      jobs: { ...state.jobs, [job.id]: job },
    })),

  syncJobs: (polled) =>
    set((state) => {
      const next: Record<number, DownloadJobOut> = {};
      for (const job of polled) {
        next[job.id] = job;
      }
      for (const [id, job] of Object.entries(state.jobs)) {
        const numId = Number(id);
        if (!(numId in next) && !TERMINAL_STATUSES.has(job.status)) {
          next[numId] = job;
        }
      }
      return { jobs: next };
    }),

  toggleFooter: () => set((state) => ({ footerExpanded: !state.footerExpanded })),

  clearCompleted: () =>
    set((state) => {
      const filtered: Record<number, DownloadJobOut> = {};
      for (const [id, job] of Object.entries(state.jobs)) {
        if (!TERMINAL_STATUSES.has(job.status)) {
          filtered[Number(id)] = job;
        }
      }
      return { jobs: filtered };
    }),

  reset: () => set({ jobs: {}, footerExpanded: false }),
}));
