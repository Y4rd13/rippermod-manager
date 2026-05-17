import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type ModViewMode = "grid" | "list";

interface UIState {
  sidebarCollapsed: boolean;
  activeGameName: string | null;
  viewModeByTab: Record<string, ModViewMode>;
  toggleSidebar: () => void;
  setActiveGame: (name: string | null) => void;
  setViewMode: (tabKey: string, mode: ModViewMode) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      activeGameName: null,
      viewModeByTab: {},
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setActiveGame: (name) => set({ activeGameName: name }),
      setViewMode: (tabKey, mode) =>
        set((s) => ({ viewModeByTab: { ...s.viewModeByTab, [tabKey]: mode } })),
    }),
    {
      name: "rmm-ui",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        viewModeByTab: state.viewModeByTab,
      }),
    },
  ),
);
