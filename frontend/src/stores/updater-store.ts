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

  setStatus: (status: UpdateStatus) => void;
  setUpdateInfo: (info: UpdateInfo | null) => void;
  setError: (error: string | null, kind?: ErrorKind) => void;
  setDownloadProgress: (progress: number | null) => void;
  reset: () => void;
}

export const useUpdaterStore = create<UpdaterState>((set) => ({
  status: "idle",
  updateInfo: null,
  error: null,
  errorKind: null,
  downloadProgress: null,

  setStatus: (status) => set({ status }),
  setUpdateInfo: (updateInfo) => set({ updateInfo }),
  setError: (error, kind) => set({ error, errorKind: kind ?? null }),
  setDownloadProgress: (downloadProgress) => set({ downloadProgress }),
  reset: () =>
    set({ status: "idle", updateInfo: null, error: null, errorKind: null, downloadProgress: null }),
}));
