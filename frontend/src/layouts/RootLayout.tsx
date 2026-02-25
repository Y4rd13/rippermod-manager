import { useEffect, useRef, useState } from "react";
import { Outlet } from "react-router";

import { ChatPanel } from "@/components/chat/ChatPanel";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Sidebar } from "@/components/layout/Sidebar";
import { Titlebar } from "@/components/layout/Titlebar";
import { KeyboardShortcutsModal } from "@/components/ui/KeyboardShortcutsModal";
import { ToastContainer } from "@/components/ui/Toast";
import { useAppUpdater } from "@/hooks/use-app-updater";
import { useHasOpenaiKey } from "@/hooks/queries";
import { ScrollContainerContext } from "@/hooks/use-scroll-container";
import { useUIStore } from "@/stores/ui-store";

export function RootLayout() {
  useAppUpdater();
  const toggleChatPanel = useUIStore((s) => s.toggleChatPanel);
  const setChatPanelOpen = useUIStore((s) => s.setChatPanelOpen);
  const hasOpenaiKey = useHasOpenaiKey();
  const hasOpenaiKeyRef = useRef(hasOpenaiKey);
  useEffect(() => { hasOpenaiKeyRef.current = hasOpenaiKey; }, [hasOpenaiKey]);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        if (!hasOpenaiKeyRef.current) return;
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
        const openDialog = document.querySelector("[role='dialog']");
        if (openDialog && !openDialog.querySelector("#shortcuts-title")) return;
        setShowShortcuts((prev) => !prev);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [toggleChatPanel, setChatPanelOpen]);

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:rounded-lg focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white focus:outline-none"
      >
        Skip to content
      </a>
      <Titlebar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main ref={mainRef} id="main-content" className="flex-1 overflow-y-auto bg-surface-0 p-6">
          <ScrollContainerContext value={mainRef}>
            <ErrorBoundary>
              <Outlet />
            </ErrorBoundary>
          </ScrollContainerContext>
        </main>
        <ChatPanel />
      </div>
      <ToastContainer />
      {showShortcuts && <KeyboardShortcutsModal onClose={() => setShowShortcuts(false)} />}
    </div>
  );
}
