import { create } from "zustand";

interface UIState {
  sidebarCollapsed: boolean;
  chatPanelOpen: boolean;
  activeGameName: string | null;
  toggleSidebar: () => void;
  toggleChatPanel: () => void;
  setChatPanelOpen: (open: boolean) => void;
  setActiveGame: (name: string | null) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  chatPanelOpen: false,
  activeGameName: null,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  toggleChatPanel: () => set((s) => ({ chatPanelOpen: !s.chatPanelOpen })),
  setChatPanelOpen: (open) => set({ chatPanelOpen: open }),
  setActiveGame: (name) => set({ activeGameName: name }),
}));
