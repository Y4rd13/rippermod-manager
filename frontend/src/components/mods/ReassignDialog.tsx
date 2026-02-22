import { Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { useReassignCorrelation } from "@/hooks/mutations";
import { useSearchNexusDownloads } from "@/hooks/queries";
import type { NexusDownloadBrief } from "@/types/api";

const NEXUS_URL_RE = /nexusmods\.com\/\w+\/mods\/(\d+)/;

function parseModId(value: string): number | null {
  const urlMatch = value.match(NEXUS_URL_RE);
  if (urlMatch) return Number(urlMatch[1]);
  const asNum = Number(value);
  if (value && Number.isInteger(asNum) && asNum > 0) return asNum;
  return null;
}

interface Props {
  gameName: string;
  modGroupId: number;
  onClose: () => void;
}

export function ReassignDialog({ gameName, modGroupId, onClose }: Props) {
  const [input, setInput] = useState("");
  const [debouncedInput, setDebouncedInput] = useState("");
  const [selected, setSelected] = useState<NexusDownloadBrief | null>(null);
  const reassign = useReassignCorrelation();
  const inputRef = useRef<HTMLInputElement>(null);

  const manualId = useMemo(() => (selected ? null : parseModId(input)), [input, selected]);
  const searchQuery = manualId == null && !selected ? debouncedInput : "";

  const { data: results = [] } = useSearchNexusDownloads(gameName, searchQuery);

  useEffect(() => {
    inputRef.current?.focus();
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedInput(input.trim());
    }, 300);
    return () => clearTimeout(timer);
  }, [input]);

  const nexusModId = selected?.nexus_mod_id ?? manualId;

  function handleConfirm() {
    if (nexusModId == null) return;
    reassign.mutate(
      { gameName, modGroupId, nexusModId },
      { onSuccess: onClose },
    );
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="reassign-dialog-title"
        className="w-full max-w-md rounded-xl border border-border bg-surface-1 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 id="reassign-dialog-title" className="text-lg font-semibold text-text-primary">
            Correct Nexus Match
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-text-muted hover:text-text-primary"
          >
            <X size={16} />
          </button>
        </div>

        <p className="mb-3 text-sm text-text-secondary">
          Paste a Nexus URL, enter a mod ID, or search by name.
        </p>

        <div className="relative mb-3">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Nexus URL, mod ID, or search..."
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              setSelected(null);
            }}
            className="w-full rounded-lg border border-border bg-surface-2 py-2 pl-8 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
          />
        </div>

        {manualId && (
          <div className="mb-3 rounded-lg border border-accent/30 bg-accent/5 p-3">
            <p className="text-sm text-text-primary">
              Nexus Mod ID: <span className="font-mono font-semibold">{manualId}</span>
            </p>
            <p className="text-xs text-text-muted mt-1">
              Will fetch mod info from Nexus if not already in the database.
            </p>
          </div>
        )}

        {results.length > 0 && !manualId && !selected && (
          <div className="mb-3 max-h-48 overflow-y-auto rounded-lg border border-border bg-surface-0">
            {results.map((r) => (
              <button
                key={r.nexus_mod_id}
                type="button"
                onClick={() => {
                  setSelected(r);
                  setInput(r.mod_name);
                }}
                className="w-full px-3 py-2 text-left text-sm transition-colors hover:bg-surface-2"
              >
                <div className="font-medium text-text-primary">{r.mod_name}</div>
                <div className="text-xs text-text-muted">
                  ID: {r.nexus_mod_id} &middot; v{r.version}
                </div>
              </button>
            ))}
          </div>
        )}

        {selected && (
          <div className="mb-3 rounded-lg border border-success/30 bg-success/5 p-3">
            <p className="text-sm font-medium text-text-primary">{selected.mod_name}</p>
            <p className="text-xs text-text-muted">
              ID: {selected.nexus_mod_id} &middot; v{selected.version}
            </p>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={nexusModId == null || reassign.isPending}
            loading={reassign.isPending}
            onClick={handleConfirm}
          >
            Reassign
          </Button>
        </div>
      </div>
    </div>
  );
}
