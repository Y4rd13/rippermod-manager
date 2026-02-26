import { GitBranch } from "lucide-react";
import type React from "react";
import { useCallback, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { EmptyState } from "@/components/ui/EmptyState";
import { FilterChips } from "@/components/ui/FilterChips";
import { SearchInput } from "@/components/ui/SearchInput";
import { SkeletonCardGrid } from "@/components/ui/SkeletonCard";
import { useConflictGraph } from "@/hooks/queries";
import { useSessionState } from "@/hooks/use-session-state";
import type { ConflictGraphEdge } from "@/types/api";

import { ConflictDetailDrawer } from "./ConflictDetailDrawer";
import { ConflictEdge } from "./ConflictEdge";
import { ConflictNode } from "./ConflictNode";
import { useForceLayout } from "./use-force-layout";

const nodeTypes = { conflict: ConflictNode };
const edgeTypes = { conflict: ConflictEdge };

const SEVERITY_CHIPS = [
  { key: "all", label: "All" },
  { key: "high", label: "High (5+)" },
  { key: "medium", label: "Medium (2-4)" },
  { key: "low", label: "Low (1)" },
];

interface ConflictGraphTabProps {
  gameName: string;
}

export function ConflictGraphTab({ gameName }: ConflictGraphTabProps) {
  const { data, isLoading } = useConflictGraph(gameName);
  const [search, setSearch] = useSessionState(`conflict-search-${gameName}`, "");
  const [severity, setSeverity] = useSessionState(`conflict-severity-${gameName}`, "all");
  const [selectedEdge, setSelectedEdge] = useState<ConflictGraphEdge | null>(null);

  // Filter nodes by search text
  const filteredData = useMemo(() => {
    if (!data) return null;

    const searchLower = search.toLowerCase();
    let filteredNodes = data.nodes;
    let filteredEdges = data.edges;

    // Filter by severity
    if (severity !== "all") {
      filteredEdges = filteredEdges.filter((e) => {
        if (severity === "high") return e.weight >= 5;
        if (severity === "medium") return e.weight >= 2 && e.weight <= 4;
        return e.weight === 1;
      });
      const edgeNodeIds = new Set(filteredEdges.flatMap((e) => [e.source, e.target]));
      filteredNodes = filteredNodes.filter((n) => edgeNodeIds.has(n.id));
    }

    // Filter by search text
    if (searchLower) {
      const matchingIds = new Set(
        filteredNodes
          .filter((n) => n.label.toLowerCase().includes(searchLower))
          .map((n) => n.id),
      );
      filteredEdges = filteredEdges.filter(
        (e) => matchingIds.has(e.source) || matchingIds.has(e.target),
      );
      const edgeNodeIds = new Set(filteredEdges.flatMap((e) => [e.source, e.target]));
      filteredNodes = filteredNodes.filter((n) => edgeNodeIds.has(n.id));
    }

    return { nodes: filteredNodes, edges: filteredEdges };
  }, [data, search, severity]);

  // Layout
  const layoutNodes = useForceLayout(
    filteredData?.nodes ?? [],
    filteredData?.edges ?? [],
    900,
    600,
  );

  // Convert to React Flow format
  const rfNodes: Node[] = useMemo(() => {
    if (!filteredData) return [];
    const posMap = new Map(layoutNodes.map((p) => [p.id, p]));
    return filteredData.nodes.map((n) => {
      const pos = posMap.get(n.id);
      return {
        id: n.id,
        type: "conflict",
        position: { x: pos?.x ?? 0, y: pos?.y ?? 0 },
        data: {
          label: n.label,
          source_type: n.source_type,
          file_count: n.file_count,
          conflict_count: n.conflict_count,
          disabled: n.disabled,
        },
      };
    });
  }, [filteredData, layoutNodes]);

  const rfEdges: Edge[] = useMemo(() => {
    if (!filteredData) return [];
    return filteredData.edges.map((e) => ({
      id: `${e.source}--${e.target}`,
      source: e.source,
      target: e.target,
      type: "conflict",
      data: { weight: e.weight, shared_files: e.shared_files },
    }));
  }, [filteredData]);

  const handleEdgeClick = useCallback(
    (_event: React.MouseEvent, edge: Edge) => {
      const graphEdge = filteredData?.edges.find(
        (e) => e.source === edge.source && e.target === edge.target,
      );
      if (graphEdge) setSelectedEdge(graphEdge);
    },
    [filteredData],
  );

  const nodeNameMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const n of data?.nodes ?? []) {
      map.set(n.id, n.label);
    }
    return map;
  }, [data]);

  if (isLoading) {
    return <SkeletonCardGrid count={3} />;
  }

  if (!data || data.nodes.length === 0) {
    return (
      <EmptyState
        icon={GitBranch}
        title="No Conflicts Found"
        description="None of your mods share files with each other. Install or add more mods to see potential conflicts."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Filter mods..."
        />
        <FilterChips chips={SEVERITY_CHIPS} active={severity} onChange={setSeverity} />
      </div>

      {filteredData && filteredData.nodes.length === 0 ? (
        <EmptyState
          icon={GitBranch}
          title="No Matches"
          description="No conflicts match your current filters. Try adjusting the search or severity filter."
        />
      ) : (
        <div className="h-[600px] rounded-xl border border-border bg-surface-0 overflow-hidden">
          <ReactFlow
            nodes={rfNodes}
            edges={rfEdges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onEdgeClick={handleEdgeClick}
            fitView
            minZoom={0.2}
            maxZoom={2}
            proOptions={{ hideAttribution: false }}
          >
            <Background color="var(--color-border)" gap={20} />
            <Controls
              showInteractive={false}
              className="!bg-surface-1 !border-border !shadow-lg [&>button]:!bg-surface-2 [&>button]:!border-border [&>button]:!text-text-muted [&>button:hover]:!bg-surface-3"
            />
            <MiniMap
              nodeColor="var(--color-accent)"
              maskColor="rgba(10,10,15,0.8)"
              className="!bg-surface-1 !border-border"
            />
          </ReactFlow>
        </div>
      )}

      {selectedEdge && (
        <ConflictDetailDrawer
          sourceName={nodeNameMap.get(selectedEdge.source) ?? selectedEdge.source}
          targetName={nodeNameMap.get(selectedEdge.target) ?? selectedEdge.target}
          sharedFiles={selectedEdge.shared_files}
          onClose={() => setSelectedEdge(null)}
        />
      )}
    </div>
  );
}
