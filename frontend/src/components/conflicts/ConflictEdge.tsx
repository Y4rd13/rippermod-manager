import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";

import { cn } from "@/lib/utils";

export function ConflictEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps) {
  const weight = (data?.weight as number) ?? 1;

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  const strokeWidth = Math.min(Math.max(Math.log2(1 + weight), 1), 5);
  const opacity = Math.min(0.3 + weight * 0.1, 1);

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: selected ? "var(--color-accent)" : "var(--color-danger)",
          strokeWidth,
          opacity,
        }}
      />
      {weight > 1 && (
        <EdgeLabelRenderer>
          <div
            className={cn(
              "absolute text-[10px] font-medium px-1.5 py-0.5 rounded-full pointer-events-none",
              selected
                ? "bg-accent text-white"
                : "bg-danger/80 text-white",
            )}
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            }}
          >
            {weight}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
