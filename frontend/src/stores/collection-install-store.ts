import { create } from "zustand";

interface CollectionInstallTarget {
  gameName: string;
  slug: string;
  revision: number;
  // True when the install is re-installing an existing collection at a
  // newer revision (the "Update to rev N" path in
  // InstalledCollectionsSection). The preview dialog labels the action
  // "Update" instead of "Install" and the backend cascade-uninstalls the
  // previous install before re-running.
  forceReinstall?: boolean;
}

interface CollectionInstallState {
  target: CollectionInstallTarget | null;
  open: (target: CollectionInstallTarget) => void;
  close: () => void;
}

/**
 * Cross-component handle for the Collections install dialog flow (#222).
 *
 * Lives in Zustand so producers (NXM deep-link handler, Browse-collections
 * page, etc.) can open the flow without prop-drilling, and a single mount
 * of ``<CollectionInstallFlow />`` at the app root reads from here.
 */
export const useCollectionInstallStore = create<CollectionInstallState>((set) => ({
  target: null,
  open: (target) => set({ target }),
  close: () => set({ target: null }),
}));
