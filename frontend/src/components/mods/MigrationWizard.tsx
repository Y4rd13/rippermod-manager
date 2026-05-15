import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { type MigrationReport, useMigrateToVfs } from "@/hooks/use-deploy";

interface MigrationWizardProps {
  gameName: string;
  onDone: () => void;
}

export function MigrationWizard({ gameName, onDone }: MigrationWizardProps) {
  const migrate = useMigrateToVfs(gameName);
  const [report, setReport] = useState<MigrationReport | null>(null);

  if (report) {
    return (
      <div className="space-y-3">
        <h3 className="text-lg font-semibold text-text-primary">Migration complete</h3>
        <p className="text-sm text-text-secondary">
          Migrated {report.migrated_mods} mods ({report.migrated_files} files).
        </p>
        {report.errors.length > 0 && (
          <details>
            <summary className="text-danger text-sm cursor-pointer">
              Errors ({report.errors.length})
            </summary>
            <ul className="text-xs font-mono mt-1 space-y-0.5 text-text-muted">
              {report.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </details>
        )}
        <Button onClick={onDone}>Done</Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold text-text-primary">Migrate to clean game folder?</h3>
      <p className="text-sm text-text-secondary">
        RipperMod will move your installed mod files from the game directory to{" "}
        <code className="text-xs text-accent font-mono">downloaded_mods/</code> and link them
        back. The game sees the same files; your game folder stays clean.
      </p>
      <p className="text-xs text-text-muted">Make sure Cyberpunk 2077 is not running.</p>
      <Button
        loading={migrate.isPending}
        onClick={() =>
          migrate.mutate(undefined, {
            onSuccess: (r) => setReport(r),
          })
        }
      >
        Migrate now
      </Button>
    </div>
  );
}
