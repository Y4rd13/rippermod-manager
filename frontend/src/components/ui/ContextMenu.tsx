import type { LucideIcon } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

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
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [adjusted, setAdjusted] = useState(position);
  const [ready, setReady] = useState(false);
  const focusIndexRef = useRef(-1);

  const actionableItems = items.filter((i) => !i.separator);

  useLayoutEffect(() => {
    const el = menuRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setAdjusted({
      x: Math.min(position.x, window.innerWidth - rect.width - 8),
      y: Math.min(position.y, window.innerHeight - rect.height - 8),
    });
    setReady(true);
  }, [position]);

  useEffect(() => {
    if (ready && itemRefs.current[0]) {
      itemRefs.current[0]?.focus();
      focusIndexRef.current = 0;
    }
  }, [ready]);

  const moveFocus = useCallback(
    (delta: number) => {
      const prev = focusIndexRef.current;
      const next = (prev + delta + actionableItems.length) % actionableItems.length;
      itemRefs.current[next]?.focus();
      focusIndexRef.current = next;
    },
    [actionableItems.length],
  );

  useEffect(() => {
    const handleMouseDown = (e: MouseEvent) => {
      if (menuRef.current?.contains(e.target as Node)) return;
      onClose();
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case "Escape":
        case "Tab":
          e.preventDefault();
          onClose();
          break;
        case "ArrowDown":
          e.preventDefault();
          moveFocus(1);
          break;
        case "ArrowUp":
          e.preventDefault();
          moveFocus(-1);
          break;
        case "Home":
          e.preventDefault();
          focusIndexRef.current = 0;
          itemRefs.current[0]?.focus();
          break;
        case "End":
          e.preventDefault();
          focusIndexRef.current = actionableItems.length - 1;
          itemRefs.current[actionableItems.length - 1]?.focus();
          break;
      }
    };
    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, moveFocus, actionableItems.length]);

  const actionIndexMap = useMemo(() => {
    const map = new Map<string, number>();
    let idx = 0;
    for (const item of items) {
      if (!item.separator) map.set(item.key, idx++);
    }
    return map;
  }, [items]);

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      className="fixed z-50 min-w-[160px] rounded-lg border border-border bg-surface-1 py-1 shadow-lg animate-fade-in"
      style={{ top: adjusted.y, left: adjusted.x, visibility: ready ? "visible" : "hidden" }}
    >
      {items.map((item) => {
        if (item.separator) {
          return <div key={item.key} role="separator" className="border-t border-border my-1" />;
        }
        const idx = actionIndexMap.get(item.key)!;
        return (
          <button
            key={item.key}
            ref={(el) => { itemRefs.current[idx] = el; }}
            role="menuitem"
            tabIndex={-1}
            className={`w-full px-3 py-1.5 text-sm text-left flex items-center gap-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent ${
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
        );
      })}
    </div>,
    document.body,
  );
}
