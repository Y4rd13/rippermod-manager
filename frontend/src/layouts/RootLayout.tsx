import { useEffect, useState } from "react";
import { Outlet } from "react-router";

import { ChatPanel } from "@/components/chat/ChatPanel";
import { Sidebar } from "@/components/layout/Sidebar";
import { Titlebar } from "@/components/layout/Titlebar";
import { KeyboardShortcutsModal } from "@/components/ui/KeyboardShortcutsModal";
import { ToastContainer } from "@/components/ui/Toast";
import { useUIStore } from "@/stores/ui-store";

export function RootLayout() {
  const toggleChatPanel = useUIStore((s) => s.toggleChatPanel);
  const setChatPanelOpen = useUIStore((s) => s.setChatPanelOpen);
  const [showShortcuts, setShowShortcuts] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        toggleChatPanel();
      }
      if (e.key === "Escape" && useUIStore.getState().chatPanelOpen) {
        const activeEl = document.activeElement?.tagName;
        if (activeEl === "INPUT" || activeEl === "TEXTAREA" || activeEl === "SELECT") return;
        if (document.querySelector("[role='dialog']") || document.querySelector("[role='menu']")) return;
        setChatPanelOpen(false);
      }
      if (e.key === "?" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const tag = document.activeElement?.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
        if (document.querySelector("[role='dialog']")) return;
        setShowShortcuts((prev) => !prev);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [toggleChatPanel, setChatPanelOpen]);

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Titlebar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-surface-0 p-6">
          <Outlet />
        </main>
        <ChatPanel />
      </div>
      <ToastContainer />
      {showShortcuts && <KeyboardShortcutsModal onClose={() => setShowShortcuts(false)} />}
    </div>
  );
}
