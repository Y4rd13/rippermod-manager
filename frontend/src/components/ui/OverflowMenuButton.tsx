import { MoreHorizontal } from "lucide-react";
import { useRef, useState } from "react";

import { ContextMenu, type ContextMenuItem } from "@/components/ui/ContextMenu";

interface Props {
  items: ContextMenuItem[];
  onSelect: (key: string) => void;
}

export function OverflowMenuButton({ items, onSelect }: Props) {
  const [menuPos, setMenuPos] = useState<{ x: number; y: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (menuPos) {
      setMenuPos(null);
      return;
    }
    const rect = btnRef.current?.getBoundingClientRect();
    if (rect) {
      setMenuPos({ x: rect.left, y: rect.bottom + 4 });
    }
  };

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={handleClick}
        aria-label="More actions"
        className="rounded-md p-1 text-text-muted hover:bg-surface-2 hover:text-text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <MoreHorizontal size={16} />
      </button>
      {menuPos && (
        <ContextMenu
          items={items}
          position={menuPos}
          onSelect={onSelect}
          onClose={() => setMenuPos(null)}
        />
      )}
    </>
  );
}
