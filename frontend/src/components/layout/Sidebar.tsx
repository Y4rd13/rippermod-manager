import {
  Gamepad2,
  Home,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Settings,
} from "lucide-react";
import { NavLink } from "react-router";

import { useHasOpenaiKey } from "@/hooks/queries";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/ui-store";

const navItems = [
  { to: "/dashboard", icon: Home, label: "Dashboard" },
  { to: "/games", icon: Gamepad2, label: "Games" },
  { to: "/updates", icon: RefreshCw, label: "Updates" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar, toggleChatPanel } = useUIStore();
  const hasOpenaiKey = useHasOpenaiKey();

  return (
    <aside
      className={cn(
        "flex flex-col border-r border-border bg-surface-1 transition-all duration-200 shrink-0",
        sidebarCollapsed ? "w-14" : "w-52",
      )}
    >
      <div className="flex items-center justify-between p-3">
        <div className="flex items-center gap-2 min-w-0">
          <img src="/app-icon.png" alt="RipperMod" className="h-6 w-6 shrink-0" />
          {!sidebarCollapsed && (
            <span className="text-sm font-semibold text-text-primary truncate">
              Mod Manager
            </span>
          )}
        </div>
        <button
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      <nav className="flex-1 space-y-0.5 px-2">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-accent/10 text-accent"
                  : "text-text-secondary hover:bg-surface-2 hover:text-text-primary",
              )
            }
          >
            <Icon size={18} />
            {!sidebarCollapsed && <span className="truncate">{label}</span>}
          </NavLink>
        ))}
      </nav>

      {hasOpenaiKey && (
        <div className="border-t border-border p-2">
          <button
            onClick={toggleChatPanel}
            aria-label="Toggle chat panel"
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-text-secondary hover:bg-surface-2 hover:text-text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <MessageSquare size={18} />
            {!sidebarCollapsed && <span>Chat</span>}
          </button>
        </div>
      )}
    </aside>
  );
}
