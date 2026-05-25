import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type ModViewMode = "grid" | "list" | "compact";

interface UIState {
  sidebarCollapsed: boolean;
  activeGameName: string | null;
  viewModeByTab: Record<string, ModViewMode>;
  adoptBannerDismissedByGame: Record<string, boolean>;
  warnBeforeLaunch: boolean;
  toggleSidebar: () => void;
  setActiveGame: (name: string | null) => void;
  setViewMode: (tabKey: string, mode: ModViewMode) => void;
  dismissAdoptBanner: (gameName: string) => void;
  setWarnBeforeLaunch: (value: boolean) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      activeGameName: null,
      viewModeByTab: {},
      adoptBannerDismissedByGame: {},
      warnBeforeLaunch: true,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setActiveGame: (name) => set({ activeGameName: name }),
      setViewMode: (tabKey, mode) =>
        set((s) => ({ viewModeByTab: { ...s.viewModeByTab, [tabKey]: mode } })),
      dismissAdoptBanner: (gameName) =>
        set((s) => ({
          adoptBannerDismissedByGame: { ...s.adoptBannerDismissedByGame, [gameName]: true },
        })),
      setWarnBeforeLaunch: (value) => set({ warnBeforeLaunch: value }),
    }),
    {
      name: "rmm-ui",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        viewModeByTab: state.viewModeByTab,
        adoptBannerDismissedByGame: state.adoptBannerDismissedByGame,
        warnBeforeLaunch: state.warnBeforeLaunch,
      }),
    },
  ),
);
