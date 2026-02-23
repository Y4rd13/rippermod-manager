import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef } from "react";

import { useScrollContainer } from "@/hooks/use-scroll-container";

interface VirtualTableProps<T> {
  items: T[];
  renderHead: () => React.ReactNode;
  renderRow: (item: T, index: number) => React.ReactNode;
  estimateHeight?: number;
  overscan?: number;
  dynamicHeight?: boolean;
  remeasureDep?: unknown;
  className?: string;
}

export function VirtualTable<T>({
  items,
  renderHead,
  renderRow,
  estimateHeight = 45,
  overscan = 5,
  dynamicHeight = false,
  remeasureDep,
  className,
}: VirtualTableProps<T>) {
  const scrollContainerRef = useScrollContainer();
  const tableRef = useRef<HTMLTableElement>(null);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollContainerRef?.current ?? null,
    estimateSize: () => estimateHeight,
    overscan,
    measureElement: dynamicHeight
      ? (el) => el.getBoundingClientRect().height
      : undefined,
    scrollMargin: tableRef.current?.offsetTop ?? 0,
  });

  useEffect(() => {
    if (dynamicHeight && remeasureDep !== undefined) {
      virtualizer.measure();
    }
  }, [remeasureDep, dynamicHeight, virtualizer]);

  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  const paddingTop =
    virtualItems.length > 0
      ? virtualItems[0].start - virtualizer.options.scrollMargin
      : 0;
  const paddingBottom =
    virtualItems.length > 0
      ? totalSize - (virtualItems[virtualItems.length - 1].end - virtualizer.options.scrollMargin)
      : 0;

  return (
    <div className={className ?? "overflow-x-auto"}>
      <table ref={tableRef} className="w-full text-sm">
        <thead>{renderHead()}</thead>
        {paddingTop > 0 && (
          <tbody>
            <tr>
              <td style={{ height: paddingTop, padding: 0, border: "none" }} />
            </tr>
          </tbody>
        )}
        {virtualItems.map((virtualRow) => {
          const item = items[virtualRow.index];
          return (
            <tbody
              key={virtualRow.index}
              ref={dynamicHeight ? virtualizer.measureElement : undefined}
              data-index={virtualRow.index}
            >
              {renderRow(item, virtualRow.index)}
            </tbody>
          );
        })}
        {paddingBottom > 0 && (
          <tbody>
            <tr>
              <td style={{ height: paddingBottom, padding: 0, border: "none" }} />
            </tr>
          </tbody>
        )}
      </table>
    </div>
  );
}
