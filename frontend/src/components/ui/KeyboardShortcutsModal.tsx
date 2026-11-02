import { Keyboard, X } from "lucide-react";

import { Dialog } from "@/components/ui/Dialog";

interface Props {
  onClose: () => void;
}

const SHORTCUTS: { keys: string[]; description: string }[] = [
  { keys: ["Esc"], description: "Close dialog / menu" },
  { keys: ["?"], description: "Show keyboard shortcuts" },
];

function Kbd({ children }: { children: string }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[24px] px-1.5 py-0.5 rounded border border-border bg-surface-2 text-xs font-mono text-text-secondary">
      {children}
    </kbd>
  );
}

export function KeyboardShortcutsModal({ onClose }: Props) {
  return (
    <Dialog
      onClose={onClose}
      titleId="shortcuts-title"
      backdropClassName="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      className="w-full max-w-sm rounded-xl border border-border bg-surface-0 overflow-hidden animate-modal-in"
    >
      <div className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div className="flex items-center gap-2">
          <Keyboard size={18} className="text-accent-text" />
          <h2 id="shortcuts-title" className="text-base font-semibold text-text-primary">
            Keyboard Shortcuts
          </h2>
        </div>
        <button
          onClick={onClose}
          aria-label="Close shortcuts"
          className="rounded p-1 text-text-muted hover:text-text-primary transition-colors"
        >
          <X size={16} />
        </button>
      </div>
      <div className="px-5 py-4 space-y-3">
        {SHORTCUTS.map((s) => (
          <div key={s.description} className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">{s.description}</span>
            <div className="flex items-center gap-1">
              {s.keys.map((k, i) => (
                <span key={k} className="flex items-center gap-1">
                  {i > 0 && <span className="text-text-muted text-xs">+</span>}
                  <Kbd>{k}</Kbd>
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Dialog>
  );
}
