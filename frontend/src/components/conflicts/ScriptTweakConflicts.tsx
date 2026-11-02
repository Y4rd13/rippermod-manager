import { FileCode } from "lucide-react";
import { useMemo } from "react";

import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonTable } from "@/components/ui/SkeletonTable";
import { VirtualTable } from "@/components/ui/VirtualTable";
import { useConflictSummary } from "@/hooks/queries";
import type { ConflictEvidenceOut, ConflictKind } from "@/types/api";

const KIND_LABEL: Partial<Record<ConflictKind, string>> = {
  redscript_target: "Redscript",
  tweak_key: "TweakXL",
};

const SEVERITY_VARIANT: Record<ConflictEvidenceOut["severity"], "danger" | "warning" | "neutral"> = {
  high: "danger",
  medium: "warning",
  low: "neutral",
};

/**
 * Redscript and TweakXL conflicts from the persisted conflict engine: the method
 * or key in conflict, the mods that touch it, the winner when known, and severity.
 * The engine reindexes in the background after scan, install, uninstall and toggle.
 */
export function ScriptTweakConflicts({ gameName }: { gameName: string }) {
  const { data, isLoading } = useConflictSummary(gameName);

  const rows = useMemo(
    () => (data?.evidence ?? []).filter((e) => e.kind === "redscript_target" || e.kind === "tweak_key"),
    [data],
  );

  if (isLoading) return <SkeletonTable columns={5} />;

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={FileCode}
        title="No script or tweak conflicts found."
        description="Redscript methods and TweakXL keys touched by more than one installed mod show up here."
      />
    );
  }

  return (
    <VirtualTable
      items={rows}
      renderHead={() => (
        <tr className="border-b border-border text-left text-text-muted sticky top-0 z-10 bg-surface-0">
          <th className="py-2 pr-4">Kind</th>
          <th className="py-2 pr-4">Key</th>
          <th className="py-2 pr-4">Mods</th>
          <th className="py-2 pr-4">Winner</th>
          <th className="py-2 pr-4">Severity</th>
        </tr>
      )}
      renderRow={(e) => (
        <tr key={e.id} className="border-b border-border/50 text-sm">
          <td className="py-2 pr-4 text-text-secondary">{KIND_LABEL[e.kind] ?? e.kind}</td>
          <td className="py-2 pr-4 font-mono text-xs text-text-primary break-all">{e.key}</td>
          <td className="py-2 pr-4 text-text-muted">{e.mods.map((m) => m.name).join(", ")}</td>
          <td className="py-2 pr-4 text-text-muted">{e.winner?.name ?? "-"}</td>
          <td className="py-2 pr-4">
            <Badge variant={SEVERITY_VARIANT[e.severity]}>{e.severity}</Badge>
          </td>
        </tr>
      )}
    />
  );
}
