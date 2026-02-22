import type { LucideIcon } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

export interface ContextMenuItem {
  key: string;
  label: string;
  icon?: LucideIcon;
  variant?: "default" | "danger";
  separator?: boolean;
}

interface ContextMenuProps {
  items: ContextMenuItem[];
  position: { x: number; y: number };
  onSelect: (key: string) => void;
  onClose: () => void;
}

export function ContextMenu({ items, position, onSelect, onClose }: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [adjusted, setAdjusted] = useState(position);

  useLayoutEffect(() => {
    const el = menuRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setAdjusted({
      x: Math.min(position.x, window.innerWidth - rect.width - 8),
      y: Math.min(position.y, window.innerHeight - rect.height - 8),
    });
  }, [position]);

  useEffect(() => {
    const handleClose = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent && e.key !== "Escape") return;
      onClose();
    };
    document.addEventListener("mousedown", handleClose);
    document.addEventListener("keydown", handleClose);
    return () => {
      document.removeEventListener("mousedown", handleClose);
      document.removeEventListener("keydown", handleClose);
    };
  }, [onClose]);

  return (
    <div
      ref={menuRef}
      className="fixed z-50 min-w-[160px] rounded-lg border border-border bg-surface-1 py-1 shadow-lg animate-fade-in"
      style={{ top: adjusted.y, left: adjusted.x }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {items.map((item) =>
        item.separator ? (
          <div key={item.key} className="border-t border-border my-1" />
        ) : (
          <button
            key={item.key}
            className={`w-full px-3 py-1.5 text-sm text-left flex items-center gap-2 transition-colors ${
              item.variant === "danger"
                ? "text-danger hover:bg-danger/10"
                : "text-text-primary hover:bg-surface-2"
            }`}
            onClick={() => {
              onSelect(item.key);
              onClose();
            }}
          >
            {item.icon && <item.icon size={14} />}
            {item.label}
          </button>
        ),
      )}
    </div>
  );
}
