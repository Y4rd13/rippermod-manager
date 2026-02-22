import { getCurrentWindow } from "@tauri-apps/api/window";
import { Minus, Square, X } from "lucide-react";

export function Titlebar() {
  const appWindow = getCurrentWindow();

  return (
    <div
      data-tauri-drag-region
      className="flex h-9 items-center justify-between border-b border-border bg-surface-0 px-3 select-none shrink-0"
    >
      <span
        data-tauri-drag-region
        className="text-xs font-semibold tracking-wide text-text-secondary"
      >
        CNMM
      </span>

      <div className="flex items-center">
        <button
          onClick={() => appWindow.minimize()}
          aria-label="Minimize window"
          className="flex h-9 w-10 items-center justify-center text-text-muted hover:bg-surface-2 hover:text-text-primary transition-colors"
        >
          <Minus size={14} />
        </button>
        <button
          onClick={() => appWindow.toggleMaximize()}
          aria-label="Maximize window"
          className="flex h-9 w-10 items-center justify-center text-text-muted hover:bg-surface-2 hover:text-text-primary transition-colors"
        >
          <Square size={12} />
        </button>
        <button
          onClick={() => appWindow.close()}
          aria-label="Close window"
          className="flex h-9 w-10 items-center justify-center text-text-muted hover:bg-danger hover:text-white transition-colors"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
