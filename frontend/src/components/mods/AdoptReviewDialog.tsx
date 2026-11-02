import { Boxes, ChevronDown, ChevronRight, Search, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { useAdoptMods } from "@/hooks/mutations";
import { plural } from "@/lib/format";
import type { AdoptGroup, ModFileOut, ModGroup } from "@/types/api";

/** Best-effort mod-type label from where the first file lives on disk. */
function inferType(files: ModFileOut[]): string {
  const p = (files[0]?.file_path ?? "").toLowerCase();
  if (p.includes("cyber_engine_tweaks/")) return "CET";
  if (p.startsWith("red4ext/")) return "RED4ext";
  if (p.startsWith("r6/scripts/")) return "redscript";
  if (p.startsWith("r6/tweaks/")) return "tweak";
  if (p.startsWith("r6/config/")) return "config";
  if (p.startsWith("mods/")) return "REDmod";
  if (p.startsWith("archive/")) return "archive";
  return "files";
}

interface Props {
  gameName: string;
  mods: ModGroup[];
  /** Rows checked when the dialog opens: the on-disk ids, or the one row the user picked. */
  preselectIds: number[];
  onClose: () => void;
}

/** A group counts as detected on disk only when the backend says so; a missing flag does not. */
const isOnDisk = (m: ModGroup) => m.nexus_match?.on_disk === true;

/**
 * Review-and-adopt dialog: lets the user pick (and rename) mods to bring under management
 * via POST /install/adopt. Mods detected on disk are listed first; weaker matches sit in a
 * collapsed "Possible matches" section. Only `preselectIds` start checked.
 */
export function AdoptReviewDialog({ gameName, mods, preselectIds, onClose }: Props) {
  const adopt = useAdoptMods();
  const [selected, setSelected] = useState<Set<number>>(() => new Set(preselectIds));
  const [possibleOpen, setPossibleOpen] = useState(() => {
    const preselected = new Set(preselectIds);
    return (
      !mods.some(isOnDisk) || mods.some((m) => !isOnDisk(m) && preselected.has(m.id))
    );
  });
  const [names, setNames] = useState<Record<number, string>>(() =>
    Object.fromEntries(mods.map((m) => [m.id, m.display_name])),
  );
  const [filter, setFilter] = useState("");

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return mods;
    return mods.filter(
      (m) =>
        m.display_name.toLowerCase().includes(q) ||
        (m.nexus_match?.mod_name ?? "").toLowerCase().includes(q),
    );
  }, [mods, filter]);

  const visibleOnDisk = visible.filter(isOnDisk);
  const visiblePossible = visible.filter((m) => !isOnDisk(m));
  // "Select all" covers the rows the user can see: possible matches only when expanded.
  const selectable = possibleOpen ? visible : visibleOnDisk;
  const allVisibleSelected =
    selectable.length > 0 && selectable.every((m) => selected.has(m.id));

  const toggleAll = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) selectable.forEach((m) => next.delete(m.id));
      else selectable.forEach((m) => next.add(m.id));
      return next;
    });
  };

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const selectedMods = mods.filter((m) => selected.has(m.id));
  const selectedFileCount = selectedMods.reduce((n, m) => n + m.files.length, 0);

  const handleAdopt = () => {
    const groups: AdoptGroup[] = selectedMods.map((m) => ({
      name: (names[m.id] ?? m.display_name).trim() || m.display_name,
      relative_paths: m.files.map((f) => f.file_path),
      nexus_mod_id: m.nexus_match?.nexus_mod_id ?? null,
    }));
    adopt.mutate(
      { gameName, groups },
      {
        onSuccess: (result) => {
          // Keep the dialog open if the game is running so the user can close it and retry.
          if (!result.game_running) onClose();
        },
      },
    );
  };

  const renderRow = (m: ModGroup) => (
    <div
      key={m.id}
      className="flex items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 py-2"
    >
      <input
        type="checkbox"
        checked={selected.has(m.id)}
        onChange={() => toggle(m.id)}
        aria-label={`Adopt ${m.display_name}`}
        className="h-4 w-4 shrink-0 accent-accent"
      />
      <input
        type="text"
        value={names[m.id] ?? m.display_name}
        onChange={(e) => setNames((p) => ({ ...p, [m.id]: e.target.value }))}
        title="Rename before adopting"
        className="min-w-0 flex-1 rounded border border-transparent bg-transparent px-1 py-0.5 text-sm font-medium text-text-primary hover:border-border focus:border-accent focus:bg-surface-1 focus:outline-none"
      />
      <Badge variant="neutral">{inferType(m.files)}</Badge>
      <span className="shrink-0 text-xs text-text-muted">
        {plural(m.files.length, "file")}
      </span>
      {m.nexus_match ? (
        <Badge
          variant={
            m.nexus_match.score >= 0.9
              ? "success"
              : m.nexus_match.score >= 0.75
                ? "warning"
                : "danger"
          }
          title={`Matched to ${m.nexus_match.mod_name}`}
        >
          {Math.round(m.nexus_match.score * 100)}%
        </Badge>
      ) : (
        <Badge variant="neutral" title="No Nexus match, adopted as a local mod">
          local
        </Badge>
      )}
    </div>
  );

  return (
    <Dialog
      onClose={onClose}
      titleId="adopt-dialog-title"
      closeOnEscape={!adopt.isPending}
      backdropClassName="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl border border-border bg-surface-1"
    >
      <div className="flex items-start justify-between border-b border-border p-5">
        <div className="flex items-center gap-2">
          <Boxes size={18} className="mt-0.5 shrink-0 text-accent-text" />
          <div>
            <h3 id="adopt-dialog-title" className="text-lg font-semibold text-text-primary">
              Adopt your existing mods
            </h3>
            <p className="mt-0.5 text-xs text-text-muted">
              Bring mods detected on disk under management, without re-downloading.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-text-muted hover:text-text-primary"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        <p className="mb-4 rounded-lg border border-border bg-surface-2 p-3 text-xs text-text-secondary">
          Adopting <span className="font-medium text-text-primary">moves</span> these files into
          managed storage and hardlinks them back, so the game sees the exact same files, nothing is
          re-extracted or reordered, and your existing configs are preserved.
        </p>

        <div className="mb-3 flex items-center justify-between gap-3">
          <label className="flex cursor-pointer select-none items-center gap-2 text-sm text-text-secondary">
            <input
              type="checkbox"
              checked={allVisibleSelected}
              onChange={toggleAll}
              className="h-4 w-4 accent-accent"
            />
            Select all ({selectable.length})
          </label>
          <div className="relative w-48">
            <Search
              size={13}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"
            />
            <input
              type="text"
              placeholder="Filter…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-full rounded-lg border border-border bg-surface-2 py-1.5 pl-8 pr-3 text-xs text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
            />
          </div>
        </div>

        <div className="space-y-4">
          {visibleOnDisk.length > 0 && (
            <section aria-labelledby="adopt-on-disk-title" className="space-y-1.5">
              <h4 id="adopt-on-disk-title" className="text-xs font-medium text-text-secondary">
                Detected on disk ({visibleOnDisk.length})
              </h4>
              {visibleOnDisk.map((m) => renderRow(m))}
            </section>
          )}
          {visiblePossible.length > 0 && (
            <section className="space-y-1.5">
              <button
                type="button"
                aria-expanded={possibleOpen}
                onClick={() => setPossibleOpen((o) => !o)}
                className="flex items-center gap-1 rounded text-xs font-medium text-text-secondary hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                {possibleOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                Possible matches ({visiblePossible.length})
              </button>
              {possibleOpen && visiblePossible.map((m) => renderRow(m))}
            </section>
          )}
          {visible.length === 0 && (
            <p className="py-8 text-center text-sm text-text-muted">No mods match the filter.</p>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-border p-5">
        <p className="text-xs text-text-muted">
          ⚠ Close Cyberpunk 2077 first · a save backup is taken automatically.
        </p>
        <div className="flex shrink-0 gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={selectedMods.length === 0 || adopt.isPending}
            loading={adopt.isPending}
            onClick={handleAdopt}
          >
            {selectedMods.length === 0
              ? "Select mods to adopt"
              : `Adopt ${plural(selectedMods.length, "mod")} (${plural(selectedFileCount, "file")})`}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
