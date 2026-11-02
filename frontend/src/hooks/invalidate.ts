import type { QueryClient } from "@tanstack/react-query";

/**
 * Query keys derived from what is installed, on disk or matched: the single
 * conflict number and inbox (``["conflicts", g]`` is a prefix of the inbox, the
 * count and per-mod detail), the conflict summary, graph and archive panels,
 * and Health. Anything that installs, uninstalls, toggles, adopts or rescans
 * must refresh all of them, or the header cards, tab badges and Dashboard keep
 * the old number while the lists already show the new state.
 */
export const CONFLICT_KEYS = [
  "conflicts",
  "conflict-summary",
  "conflict-graph",
  "archive-conflict-summaries",
  "archive-resource-details",
] as const;

const DERIVED_KEYS = [...CONFLICT_KEYS, "health"] as const;

/** Refetch every conflict view of a game (also run when the background reindex ends). */
export function invalidateConflictViews(qc: QueryClient, gameName: string | null): void {
  for (const key of CONFLICT_KEYS) {
    void qc.invalidateQueries({ queryKey: [key, gameName] });
  }
}

export function invalidateGameState(qc: QueryClient, gameName: string | null): void {
  for (const key of DERIVED_KEYS) {
    void qc.invalidateQueries({ queryKey: [key, gameName] });
  }
  // The change just made queued a background conflict reindex: poll its status so
  // the conflict views refetch again when it ends.
  void qc.invalidateQueries({ queryKey: ["conflict-reindex-status", gameName] });
}
