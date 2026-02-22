import { useEffect, useState } from "react";

const WIDTHS = ["w-2/3", "w-1/2", "w-3/4", "w-1/3", "w-2/5"];

function computeRows() {
  return Math.max(3, Math.floor((window.innerHeight - 300) / 44));
}

export function SkeletonTable({ columns = 5, rows }: { columns?: number; rows?: number }) {
  const [autoRows, setAutoRows] = useState(computeRows);

  useEffect(() => {
    if (rows != null) return;
    const onResize = () => setAutoRows(computeRows());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [rows]);

  const effectiveRows = rows ?? autoRows;
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-border text-left">
          {Array.from({ length: columns }, (_, i) => (
            <th key={i} className="pb-2 pr-4">
              <div className="h-3 bg-surface-2 animate-pulse rounded w-20" />
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {Array.from({ length: effectiveRows }, (_, r) => (
          <tr key={r} className="border-b border-border/50">
            {Array.from({ length: columns }, (_, c) => (
              <td key={c} className="py-3 pr-4">
                <div
                  className={`h-3 bg-surface-2 animate-pulse rounded ${WIDTHS[(r + c) % WIDTHS.length]}`}
                />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
