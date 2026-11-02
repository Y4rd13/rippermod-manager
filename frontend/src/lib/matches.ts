import type { ModGroup } from "@/types/api";

/**
 * The "Nexus Matched" number: scanned mods whose Nexus match is trusted, i.e. the backend's
 * `on_disk` (user-confirmed, or a score of at least 0.75). Low-confidence matches stay listed
 * in the Matched tab for review but are not counted.
 */
export function countTrustedMatches(mods: Pick<ModGroup, "nexus_match">[]): number {
  return mods.filter((m) => m.nexus_match?.on_disk === true).length;
}
