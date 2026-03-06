import { create } from "zustand";

export type UpdateStatus =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "up-to-date"
  | "ready"
  | "error";

export type ErrorKind = "network" | "generic";

export interface UpdateInfo {
  version: string;
  date: string | null;
  body: string | null;
}

interface UpdaterState {
  status: UpdateStatus;
  updateInfo: UpdateInfo | null;
  error: string | null;
  errorKind: ErrorKind | null;
  downloadProgress: number | null;
  bannerDismissed: boolean;

  setStatus: (status: UpdateStatus) => void;
  setUpdateInfo: (info: UpdateInfo | null) => void;
  setError: (error: string | null, kind?: ErrorKind) => void;
  setDownloadProgress: (progress: number | null) => void;
  dismissBanner: () => void;
  reset: () => void;
}

export const useUpdaterStore = create<UpdaterState>((set) => ({
  status: "idle",
  updateInfo: null,
  error: null,
  errorKind: null,
  downloadProgress: null,
  bannerDismissed: false,

  setStatus: (status) => set({ status }),
  setUpdateInfo: (updateInfo) => set({ updateInfo, bannerDismissed: false }),
  setError: (error, kind) => set({ error, errorKind: kind ?? null }),
  setDownloadProgress: (downloadProgress) => set({ downloadProgress }),
  dismissBanner: () => set({ bannerDismissed: true }),
  reset: () =>
    set({ status: "idle", updateInfo: null, error: null, errorKind: null, downloadProgress: null, bannerDismissed: false }),
}));
