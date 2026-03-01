import { FileWarning, Layers, Network, Package } from "lucide-react";
import { useMemo } from "react";

import { Badge } from "@/components/ui/Badge";
import { useConflictGraph } from "@/hooks/queries";
import type { ConflictGraphEdge, ConflictGraphNode } from "@/types/api";

type ClusterSeverity = "critical" | "warning" | "info";

interface Cluster {
  modNames: string[];
  fileConflicts: number;
  resourceConflicts: number;
  realResourceCount: number;
  identicalResourceCount: number;
  severity: ClusterSeverity;
}

function findClusters(nodes: ConflictGraphNode[], edges: ConflictGraphEdge[]): Cluster[] {
  const parent = new Map<string, string>();
  const rank = new Map<string, number>();

  for (const node of nodes) {
    parent.set(node.id, node.id);
    rank.set(node.id, 0);
  }

  function find(x: string): string {
    let root = x;
    while (parent.get(root) !== root) root = parent.get(root)!;
    let curr = x;
    while (curr !== root) {
      const next = parent.get(curr)!;
      parent.set(curr, root);
      curr = next;
    }
    return root;
  }

  function union(a: string, b: string) {
    const ra = find(a);
    const rb = find(b);
    if (ra === rb) return;
    const rankA = rank.get(ra)!;
    const rankB = rank.get(rb)!;
    if (rankA < rankB) {
      parent.set(ra, rb);
    } else if (rankA > rankB) {
      parent.set(rb, ra);
    } else {
      parent.set(rb, ra);
      rank.set(ra, rankA + 1);
    }
  }

  for (const edge of edges) {
    union(edge.source, edge.target);
  }

  const groups = new Map<string, string[]>();
  for (const node of nodes) {
    const root = find(node.id);
    const group = groups.get(root);
    if (group) {
      group.push(node.id);
    } else {
      groups.set(root, [node.id]);
    }
  }

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  const clusters: Cluster[] = [];
  for (const memberIds of groups.values()) {
    if (memberIds.length < 2) continue;

    const memberSet = new Set(memberIds);
    const clusterEdges = edges.filter(
      (e) => memberSet.has(e.source) && memberSet.has(e.target),
    );

    let fileConflicts = 0;
    let resourceConflicts = 0;
    let realResourceCount = 0;
    let identicalResourceCount = 0;

    for (const edge of clusterEdges) {
      fileConflicts += edge.weight;
      resourceConflicts += edge.resource_conflicts;
      realResourceCount += edge.real_resource_count;
      identicalResourceCount += edge.identical_resource_count;
    }

    const severity: ClusterSeverity =
      realResourceCount > 0 ? "critical" : resourceConflicts > 0 ? "warning" : "info";

    clusters.push({
      modNames: memberIds.map((id) => nodeMap.get(id)?.label ?? id),
      fileConflicts,
      resourceConflicts,
      realResourceCount,
      identicalResourceCount,
      severity,
    });
  }

  const severityOrder: Record<ClusterSeverity, number> = { critical: 0, warning: 1, info: 2 };
  clusters.sort((a, b) => {
    const s = severityOrder[a.severity] - severityOrder[b.severity];
    if (s !== 0) return s;
    return b.fileConflicts + b.resourceConflicts - (a.fileConflicts + a.resourceConflicts);
  });

  return clusters;
}

const severityBorder: Record<ClusterSeverity, string> = {
  critical: "border-l-danger bg-danger/5",
  warning: "border-l-warning bg-warning/5",
  info: "border-l-accent bg-accent/5",
};

const severityBadge: Record<ClusterSeverity, "danger" | "warning" | "neutral"> = {
  critical: "danger",
  warning: "warning",
  info: "neutral",
};

const MAX_VISIBLE_CLUSTERS = 3;

const statCardConfig = [
  { key: "fileConflicts", label: "File Conflicts", Icon: FileWarning, color: "text-warning" },
  { key: "resourceConflicts", label: "Resource Conflicts", Icon: Layers, color: "text-danger" },
  { key: "clusters", label: "Clusters", Icon: Network, color: "text-accent" },
  { key: "mods", label: "Mods", Icon: Package, color: "text-text-muted" },
] as const;

interface Props {
  gameName: string;
}

export function ConflictSummaryWidget({ gameName }: Props) {
  const { data: graph, isLoading } = useConflictGraph(gameName);

  const clusters = useMemo(() => {
    if (!graph) return [];
    return findClusters(graph.nodes, graph.edges);
  }, [graph]);

  const stats = useMemo(() => {
    if (!graph) return null;
    const totalFileConflicts = graph.edges.reduce((s, e) => s + e.weight, 0);
    const totalResourceConflicts = graph.edges.reduce((s, e) => s + e.resource_conflicts, 0);
    return {
      fileConflicts: totalFileConflicts,
      resourceConflicts: totalResourceConflicts,
      clusters: clusters.length,
      mods: graph.nodes.length,
    };
  }, [graph, clusters]);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="rounded-lg bg-surface-2 p-3 animate-pulse">
            <div className="h-5 w-8 bg-surface-3 rounded mb-1" />
            <div className="h-3 w-16 bg-surface-3 rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (!graph || graph.nodes.length === 0 || !stats) return null;

  const visibleClusters = clusters.slice(0, MAX_VISIBLE_CLUSTERS);
  const hiddenCount = clusters.length - MAX_VISIBLE_CLUSTERS;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {statCardConfig.map(({ key, label, Icon, color }) => (
          <div
            key={key}
            className="rounded-lg border border-border bg-surface-2 px-3 py-2.5"
          >
            <div className="flex items-center gap-2">
              <Icon size={14} className={`${color} shrink-0`} />
              <div className="min-w-0">
                <p className="text-lg font-bold text-text-primary leading-tight tabular-nums">
                  {stats[key]}
                </p>
                <p className="text-xs text-text-muted truncate">{label}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {visibleClusters.length > 0 && (
        <div className="space-y-1.5">
          {visibleClusters.map((cluster, i) => (
            <div
              key={i}
              className={`flex items-center gap-2 text-sm rounded-r-md border-l-2 px-2.5 py-1.5 ${severityBorder[cluster.severity]}`}
            >
              <span className="truncate text-text-primary">
                {cluster.modNames.join(", ")}
              </span>
              <span className="ml-auto flex items-center gap-1.5 shrink-0">
                {cluster.realResourceCount > 0 && (
                  <Badge variant={severityBadge[cluster.severity]}>
                    {cluster.realResourceCount} real
                  </Badge>
                )}
                {cluster.identicalResourceCount > 0 && (
                  <Badge variant="warning">
                    {cluster.identicalResourceCount} cosmetic
                  </Badge>
                )}
                {(cluster.resourceConflicts === 0 || (cluster.realResourceCount === 0 && cluster.identicalResourceCount === 0)) && cluster.fileConflicts > 0 && (
                  <Badge variant="neutral">
                    {cluster.fileConflicts} file overlap{cluster.fileConflicts !== 1 ? "s" : ""}
                  </Badge>
                )}
              </span>
            </div>
          ))}
          {hiddenCount > 0 && (
            <p className="text-xs text-text-muted pl-3">
              +{hiddenCount} more cluster{hiddenCount !== 1 ? "s" : ""}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
