import { create } from "zustand";

interface UIState {
  sidebarCollapsed: boolean;
  activeGameName: string | null;
  toggleSidebar: () => void;
  setActiveGame: (name: string | null) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  activeGameName: null,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setActiveGame: (name) => set({ activeGameName: name }),
}));
