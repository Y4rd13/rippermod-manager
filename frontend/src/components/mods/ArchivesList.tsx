import { AlertTriangle, Download } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import {
  useCheckConflicts,
  useInstallMod,
} from "@/hooks/mutations";
import type {
  AvailableArchive,
  ConflictCheckResult,
} from "@/types/api";

interface Props {
  archives: AvailableArchive[];
  gameName: string;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function ArchivesList({ archives, gameName }: Props) {
  const installMod = useInstallMod();
  const checkConflicts = useCheckConflicts();
  const [conflicts, setConflicts] = useState<ConflictCheckResult | null>(null);
  const [selectedArchive, setSelectedArchive] = useState<string | null>(null);

  const handleCheckConflicts = async (filename: string) => {
    setSelectedArchive(filename);
    const result = await checkConflicts.mutateAsync({
      gameName,
      archiveFilename: filename,
    });
    if (result.conflicts.length > 0) {
      setConflicts(result);
    } else {
      installMod.mutate({
        gameName,
        data: { archive_filename: filename, skip_conflicts: [] },
      });
    }
  };

  const handleInstallWithSkip = () => {
    if (!conflicts) return;
    installMod.mutate({
      gameName,
      data: {
        archive_filename: conflicts.archive_filename,
        skip_conflicts: conflicts.conflicts.map((c) => c.file_path),
      },
    });
    setConflicts(null);
    setSelectedArchive(null);
  };

  const handleInstallOverwrite = () => {
    if (!conflicts) return;
    installMod.mutate({
      gameName,
      data: { archive_filename: conflicts.archive_filename, skip_conflicts: [] },
    });
    setConflicts(null);
    setSelectedArchive(null);
  };

  if (archives.length === 0) {
    return (
      <p className="py-4 text-sm text-text-muted">
        No archives found. Place mod archives (.zip, .7z, .rar) in the
        &quot;downloaded_mods&quot; folder inside the game directory.
      </p>
    );
  }

  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text-muted">
              <th className="pb-2 pr-4">Archive</th>
              <th className="pb-2 pr-4">Parsed Name</th>
              <th className="pb-2 pr-4">Version</th>
              <th className="pb-2 pr-4">Size</th>
              <th className="pb-2 pr-4">Nexus ID</th>
              <th className="pb-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {archives.map((a) => (
              <tr key={a.filename} className="border-b border-border/50">
                <td className="py-2 pr-4 font-mono text-xs text-text-primary max-w-[200px] truncate">
                  {a.filename}
                </td>
                <td className="py-2 pr-4 text-text-secondary">
                  {a.parsed_name}
                </td>
                <td className="py-2 pr-4 text-text-muted">
                  {a.parsed_version ?? "--"}
                </td>
                <td className="py-2 pr-4 text-text-muted">
                  {formatBytes(a.size)}
                </td>
                <td className="py-2 pr-4 text-text-muted">
                  {a.nexus_mod_id ?? "--"}
                </td>
                <td className="py-2 text-right">
                  <Button
                    size="sm"
                    loading={
                      (checkConflicts.isPending || installMod.isPending) &&
                      selectedArchive === a.filename
                    }
                    onClick={() => handleCheckConflicts(a.filename)}
                  >
                    <Download size={14} /> Install
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {conflicts && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg rounded-xl border border-border bg-surface-1 p-6">
            <div className="mb-4 flex items-center gap-2 text-warning">
              <AlertTriangle size={20} />
              <h3 className="text-lg font-semibold text-text-primary">
                File Conflicts Detected
              </h3>
            </div>
            <p className="mb-3 text-sm text-text-secondary">
              {conflicts.conflicts.length} file(s) conflict with installed mods:
            </p>
            <div className="mb-4 max-h-48 overflow-y-auto rounded border border-border bg-surface-0 p-3">
              {conflicts.conflicts.map((c) => (
                <div key={c.file_path} className="py-1 text-xs">
                  <span className="font-mono text-text-primary">
                    {c.file_path}
                  </span>
                  <span className="ml-2 text-text-muted">
                    (owned by {c.owning_mod_name})
                  </span>
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setConflicts(null);
                  setSelectedArchive(null);
                }}
              >
                Cancel
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleInstallWithSkip}
              >
                Skip Conflicts
              </Button>
              <Button size="sm" onClick={handleInstallOverwrite}>
                Overwrite
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
