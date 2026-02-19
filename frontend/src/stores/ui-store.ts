import { create } from "zustand";

interface UIState {
  sidebarCollapsed: boolean;
  chatPanelOpen: boolean;
  toggleSidebar: () => void;
  toggleChatPanel: () => void;
  setChatPanelOpen: (open: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  chatPanelOpen: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  toggleChatPanel: () => set((s) => ({ chatPanelOpen: !s.chatPanelOpen })),
  setChatPanelOpen: (open) => set({ chatPanelOpen: open }),
}));
