import { Loader2, Shuffle } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { useArchiveResourceDetails } from "@/hooks/queries";
import type { ResourceConflictGroup } from "@/types/api";

interface Props {
  gameName: string;
  archiveFilename: string;
}

function GroupSection({ group }: { group: ResourceConflictGroup }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 flex-wrap">
        <code className="font-mono text-accent text-xs">{group.partner_archive}</code>
        {group.partner_mod_name && (
          <span className="text-text-muted text-xs">({group.partner_mod_name})</span>
        )}
        {group.is_winner ? (
          <Badge variant="success">wins over</Badge>
        ) : (
          <Badge variant="danger">loses to</Badge>
        )}
        <span className="text-xs text-text-muted ml-auto">
          {group.real_count > 0 && (
            <span className="text-danger">{group.real_count} real</span>
          )}
          {group.real_count > 0 && group.identical_count > 0 && ", "}
          {group.identical_count > 0 && (
            <span className="text-text-muted">{group.identical_count} cosmetic</span>
          )}
        </span>
      </div>

      <div className="space-y-0.5">
        {group.resources.map((r) => (
          <div
            key={r.resource_hash}
            className="flex items-center gap-2 text-xs text-text-secondary pl-2"
          >
            <Shuffle size={10} className="text-text-muted shrink-0" />
            <code className="font-mono text-text-primary">{r.resource_hash}</code>
            {r.is_identical ? (
              <Badge variant="success">cosmetic</Badge>
            ) : (
              <Badge variant="danger">real</Badge>
            )}
            <span className="text-text-muted">winner: {r.winner_archive}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ResourceDetailsPanel({ gameName, archiveFilename }: Props) {
  const { data, isLoading, isError } = useArchiveResourceDetails(gameName, archiveFilename);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-3 text-xs text-text-muted">
        <Loader2 size={14} className="animate-spin" />
        Loading resource details...
      </div>
    );
  }

  if (isError || !data) {
    return (
      <p className="py-2 text-xs text-danger">Failed to load resource details.</p>
    );
  }

  if (data.groups.length === 0) {
    return (
      <p className="py-2 text-xs text-text-muted">No resource-level conflict details available.</p>
    );
  }

  return (
    <div className="max-h-64 overflow-y-auto space-y-3 rounded border border-border p-3 bg-surface-0 mt-2">
      {data.groups.map((group) => (
        <GroupSection key={group.partner_archive} group={group} />
      ))}
    </div>
  );
}
