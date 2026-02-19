import { Outlet } from "react-router";

import { ChatPanel } from "@/components/chat/ChatPanel";
import { Sidebar } from "@/components/layout/Sidebar";
import { Titlebar } from "@/components/layout/Titlebar";

export function RootLayout() {
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
    </div>
  );
}
