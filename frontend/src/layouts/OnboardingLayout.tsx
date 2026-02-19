import { Outlet } from "react-router";

import { Titlebar } from "@/components/layout/Titlebar";

export function OnboardingLayout() {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Titlebar />
      <main className="flex-1 overflow-y-auto bg-surface-0">
        <Outlet />
      </main>
    </div>
  );
}
