/**
 * Human-readable labels for internal enum values the backend sends.
 * The UI never prints a raw key: unknown values fall back to Title Case.
 */

/** Every value the backend writes to `ModNexusCorrelation.method`. */
const MATCH_METHOD_LABELS: Record<string, string> = {
  filename_id: "Filename ID",
  exact: "Exact name",
  substring: "Name contains",
  fuzzy: "Name similarity",
  file_content: "File contents",
  file_list: "File list",
  endorsed_name: "Endorsed (name)",
  requirement: "Requirement of another mod",
  collection: "Collection",
  manual: "Set by you",
  installed: "Installed",
  fomod: "FOMOD",
};

/** Activity log actions (`ActivityLogEntry.action`). */
const ACTIVITY_LABELS: Record<string, string> = {
  install: "Installed",
  uninstall: "Uninstalled",
  enable: "Enabled",
  disable: "Disabled",
  deploy: "Deployed",
  undeploy: "Undeployed",
  download: "Downloaded",
  undo: "Undid",
  adopt: "Adopted",
};

const warnedKeys = new Set<string>();

/** `web_search_v2` -> `Web Search V2`. */
export function titleCaseKey(key: string): string {
  return key
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function labelFor(map: Record<string, string>, kind: string, key: string | null | undefined): string {
  if (!key) return "Unknown";
  const known = map[key];
  if (known) return known;
  const warnKey = `${kind}:${key}`;
  if (!warnedKeys.has(warnKey)) {
    warnedKeys.add(warnKey);
    console.warn(`No label for ${kind} "${key}"`);
  }
  return titleCaseKey(key) || "Unknown";
}

export function matchMethodLabel(method: string | null | undefined): string {
  return labelFor(MATCH_METHOD_LABELS, "match method", method);
}

export function activityLabel(action: string): string {
  return labelFor(ACTIVITY_LABELS, "activity action", action);
}
