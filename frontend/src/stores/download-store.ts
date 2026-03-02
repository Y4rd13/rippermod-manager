import { create } from "zustand";

import type { DownloadJobOut } from "@/types/api";

export const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

const STALE_CYCLE_LIMIT = 3;

interface DownloadState {
  jobs: Record<number, DownloadJobOut>;
  /** Counts how many sync cycles a local-only job has been absent from polled data. */
  missCounts: Record<number, number>;
  footerExpanded: boolean;
  setJob: (job: DownloadJobOut) => void;
  syncJobs: (polled: DownloadJobOut[]) => void;
  toggleFooter: () => void;
  clearCompleted: () => void;
  reset: () => void;
}

export const useDownloadStore = create<DownloadState>((set) => ({
  jobs: {},
  missCounts: {},
  footerExpanded: false,

  setJob: (job) =>
    set((state) => ({
      jobs: { ...state.jobs, [job.id]: job },
    })),

  syncJobs: (polled) =>
    set((state) => {
      const next: Record<number, DownloadJobOut> = {};
      const nextMisses: Record<number, number> = {};
      const polledIds = new Set<number>();

      for (const job of polled) {
        // Only add terminal jobs if they already exist in the store
        // (i.e. the user witnessed them transition from active → terminal).
        // This prevents cleared items from being re-inserted by future polls.
        if (TERMINAL_STATUSES.has(job.status) && !(job.id in state.jobs)) continue;
        next[job.id] = job;
        polledIds.add(job.id);
      }

      for (const [id, job] of Object.entries(state.jobs)) {
        const numId = Number(id);
        if (polledIds.has(numId) || TERMINAL_STATUSES.has(job.status)) continue;
        const misses = (state.missCounts[numId] ?? 0) + 1;
        if (misses < STALE_CYCLE_LIMIT) {
          next[numId] = job;
          nextMisses[numId] = misses;
        }
      }

      return { jobs: next, missCounts: nextMisses };
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

  reset: () => set({ jobs: {}, missCounts: {}, footerExpanded: false }),
}));
