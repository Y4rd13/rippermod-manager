import { useVirtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useColumnCount } from "@/hooks/use-column-count";
import { useScrollContainer } from "@/hooks/use-scroll-container";

interface VirtualCardGridProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  estimateHeight?: number;
  overscan?: number;
  remeasureDep?: unknown;
  className?: string;
}

export function VirtualCardGrid<T>({
  items,
  renderItem,
  estimateHeight = 296,
  overscan = 2,
  remeasureDep,
  className,
}: VirtualCardGridProps<T>) {
  const columnCount = useColumnCount();
  const scrollContainerRef = useScrollContainer();
  const listRef = useRef<HTMLDivElement>(null);
  const [scrollMargin, setScrollMargin] = useState(0);

  const listCallbackRef = useCallback((node: HTMLDivElement | null) => {
    listRef.current = node;
    setScrollMargin(node?.offsetTop ?? 0);
  }, []);

  const rows = useMemo(() => {
    const result: T[][] = [];
    for (let i = 0; i < items.length; i += columnCount) {
      result.push(items.slice(i, i + columnCount));
    }
    return result;
  }, [items, columnCount]);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollContainerRef?.current ?? null,
    estimateSize: () => estimateHeight,
    overscan,
    gap: 16,
    measureElement: (el) => el.getBoundingClientRect().height,
    scrollMargin,
  });

  useEffect(() => {
    virtualizer.measure();
    // virtualizer ref is stable from useVirtualizer — safe to omit from deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [columnCount]);

  useEffect(() => {
    if (remeasureDep !== undefined) {
      virtualizer.measure();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remeasureDep]);

  return (
    <div
      ref={listCallbackRef}
      className={className}
      style={{ height: virtualizer.getTotalSize(), position: "relative" }}
    >
      {virtualizer.getVirtualItems().map((virtualRow) => {
        const row = rows[virtualRow.index];
        return (
          <div
            key={virtualRow.index}
            ref={virtualizer.measureElement}
            data-index={virtualRow.index}
            className="grid gap-x-4"
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              transform: `translateY(${virtualRow.start - virtualizer.options.scrollMargin}px)`,
              gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))`,
            }}
          >
            {row.map((item, colIndex) => {
              const globalIndex = virtualRow.index * columnCount + colIndex;
              return (
                <div key={globalIndex} className="grid">{renderItem(item, globalIndex)}</div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
