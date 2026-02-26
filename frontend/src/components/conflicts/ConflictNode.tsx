import { Archive, Package } from "lucide-react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

import { cn } from "@/lib/utils";

export interface ConflictNodeData {
  label: string;
  source_type: string;
  file_count: number;
  conflict_count: number;
  disabled: boolean;
  [key: string]: unknown;
}

export function ConflictNode({ data, selected }: NodeProps) {
  const nodeData = data as unknown as ConflictNodeData;
  const { label, source_type, file_count, conflict_count, disabled } = nodeData;

  const ratio = file_count > 0 ? conflict_count / file_count : 0;
  const severityColor =
    ratio > 0.5
      ? "border-danger"
      : ratio > 0.2
        ? "border-warning"
        : "border-accent";

  const Icon = source_type === "installed" ? Package : Archive;

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-surface-1 px-3 py-2 min-w-[120px] max-w-[180px] transition-all",
        severityColor,
        disabled && "opacity-50",
        selected && "ring-2 ring-accent ring-offset-2 ring-offset-surface-0",
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-border !w-2 !h-2" />
      <div className="flex items-center gap-2 mb-1">
        <Icon size={14} className="shrink-0 text-text-muted" />
        <span className="text-xs font-medium text-text-primary truncate">{label}</span>
      </div>
      <div className="flex items-center gap-2 text-[10px] text-text-muted">
        <span>{conflict_count} conflicts</span>
        <span className="opacity-40">|</span>
        <span>{file_count} files</span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-border !w-2 !h-2" />
    </div>
  );
}
