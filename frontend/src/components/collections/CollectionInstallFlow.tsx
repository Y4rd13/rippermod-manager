import { useState } from "react";

import type { CollectionStatus } from "@/types/api";

import { CollectionInstallProgress } from "./CollectionInstallProgress";
import { CollectionPreviewDialog } from "./CollectionPreviewDialog";

interface Props {
  gameName: string;
  slug: string;
  revision: number;
  onClose: () => void;
}

/**
 * Controller for the Collections install user flow: preview -> progress.
 *
 * Owns the two-step state machine so callers (NXM deep-link handler,
 * Browse-collections page, etc.) only need to mount this once with the
 * target ``(gameName, slug, revision)`` triple and an ``onClose`` callback.
 *
 * The progress view subsumes the "finished" state, so when the install
 * settles the same dialog flips to a summary + Close button.
 */
export function CollectionInstallFlow({ gameName, slug, revision, onClose }: Props) {
  const [installed, setInstalled] = useState<CollectionStatus | null>(null);

  if (installed) {
    return (
      <CollectionInstallProgress
        collectionId={installed.id}
        onFinished={onClose}
        onCancel={onClose}
      />
    );
  }
  return (
    <CollectionPreviewDialog
      gameName={gameName}
      slug={slug}
      revision={revision}
      onClose={onClose}
      onInstallStarted={setInstalled}
    />
  );
}
