import type { DependentMod } from "@/types/api";

interface Props {
  dependents: DependentMod[];
}

/**
 * Warns that other installed mods declare the target mod as a requirement.
 * Reflects locally synced requirement data only — coverage depends on what has
 * been fetched from Nexus, so some dependents may not be listed.
 */
export function DependentsWarning({ dependents }: Props) {
  if (dependents.length === 0) return null;
  const count = dependents.length;
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-3">
      <p className="mb-1.5 text-xs font-medium text-warning">
        {count === 1
          ? "1 installed mod depends on this and may stop working:"
          : `${count} installed mods depend on this and may stop working:`}
      </p>
      <ul className="max-h-32 space-y-0.5 overflow-y-auto text-xs text-text-secondary">
        {dependents.map((d) => (
          <li key={d.installed_mod_id} className="truncate">
            • {d.name}
          </li>
        ))}
      </ul>
      <p className="mt-1.5 text-[10px] text-text-muted">
        Based on synced requirement data; some dependents may not be listed.
      </p>
    </div>
  );
}
