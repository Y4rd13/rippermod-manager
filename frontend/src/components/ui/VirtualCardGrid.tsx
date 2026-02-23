import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useMemo, useRef } from "react";

import { useColumnCount } from "@/hooks/use-column-count";
import { useScrollContainer } from "@/hooks/use-scroll-container";

interface VirtualCardGridProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  estimateHeight?: number;
  overscan?: number;
  dynamicHeight?: boolean;
  remeasureDep?: unknown;
  className?: string;
}

export function VirtualCardGrid<T>({
  items,
  renderItem,
  estimateHeight = 296,
  overscan = 2,
  dynamicHeight = false,
  remeasureDep,
  className,
}: VirtualCardGridProps<T>) {
  const columnCount = useColumnCount();
  const scrollContainerRef = useScrollContainer();
  const listRef = useRef<HTMLDivElement>(null);

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
    measureElement: dynamicHeight
      ? (el) => el.getBoundingClientRect().height
      : undefined,
    scrollMargin: listRef.current?.offsetTop ?? 0,
  });

  useEffect(() => {
    virtualizer.measure();
  }, [columnCount, virtualizer]);

  useEffect(() => {
    if (dynamicHeight && remeasureDep !== undefined) {
      virtualizer.measure();
    }
  }, [remeasureDep, dynamicHeight, virtualizer]);

  return (
    <div
      ref={listRef}
      className={className}
      style={{ height: virtualizer.getTotalSize(), position: "relative" }}
    >
      {virtualizer.getVirtualItems().map((virtualRow) => {
        const row = rows[virtualRow.index];
        return (
          <div
            key={virtualRow.index}
            ref={dynamicHeight ? virtualizer.measureElement : undefined}
            data-index={virtualRow.index}
            className="grid gap-x-4 mb-4"
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
                <div key={globalIndex}>{renderItem(item, globalIndex)}</div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
