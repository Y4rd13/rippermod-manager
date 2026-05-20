const VERSION_RE = /^(\d+)\.(\d+)\.(\d+)(?:-([a-z]+)(?:\.(\d+))?)?$/i;

export interface ParsedVersion {
  major: number;
  minor: number;
  patch: number;
  prerelease: string | null;
  prereleaseNum: number | null;
}

/**
 * Strip any leading non-digit prefix (e.g. ``v``, ``V``, ``nexus-v``) and any
 * trailing git-describe suffix (``-N-g<sha>``) so build-time and
 * Nexus-published version strings can be compared.
 *
 * The previous implementation only stripped a single leading ``v``/``V``, which
 * silently broke the in-app update notification for the Nexus edition. Its
 * tags are ``nexus-vX.Y.Z`` so ``__APP_VERSION__`` (set via
 * ``git describe --tags``) was something like ``"nexus-v2.11.2"`` -- which
 * failed :func:`parseVersion`'s ``/^(\d+)\.(\d+)\.(\d+).../`` regex. With both
 * sides failing to parse, :func:`compareVersions` returned ``0`` defensively
 * and the banner / toast never fired.
 */
export function normalizeVersion(raw: string): string {
  if (!raw) return "";
  let s = raw.trim();
  s = s.replace(/^[^\d]+/, "");
  s = s.replace(/-\d+-g[0-9a-f]{4,}$/i, "");
  return s;
}

export function parseVersion(raw: string): ParsedVersion | null {
  const norm = normalizeVersion(raw);
  const m = VERSION_RE.exec(norm);
  if (!m) return null;
  return {
    major: parseInt(m[1], 10),
    minor: parseInt(m[2], 10),
    patch: parseInt(m[3], 10),
    prerelease: m[4] ?? null,
    prereleaseNum: m[5] != null ? parseInt(m[5], 10) : null,
  };
}

/**
 * Returns -1 if a < b, 0 if equal, 1 if a > b. Returns 0 when either
 * side fails to parse so a malformed Nexus version string can't trigger
 * a false "update available" notification.
 *
 * Prerelease ordering follows semver: any prerelease is less than the
 * same MAJOR.MINOR.PATCH without a prerelease.
 */
export function compareVersions(a: string, b: string): number {
  const pa = parseVersion(a);
  const pb = parseVersion(b);
  if (!pa || !pb) return 0;
  if (pa.major !== pb.major) return pa.major < pb.major ? -1 : 1;
  if (pa.minor !== pb.minor) return pa.minor < pb.minor ? -1 : 1;
  if (pa.patch !== pb.patch) return pa.patch < pb.patch ? -1 : 1;
  if (pa.prerelease === null && pb.prerelease === null) return 0;
  if (pa.prerelease === null) return 1;
  if (pb.prerelease === null) return -1;
  if (pa.prerelease !== pb.prerelease) return pa.prerelease < pb.prerelease ? -1 : 1;
  const na = pa.prereleaseNum ?? 0;
  const nb = pb.prereleaseNum ?? 0;
  if (na !== nb) return na < nb ? -1 : 1;
  return 0;
}

export function isNewerVersion(current: string, latest: string): boolean {
  return compareVersions(latest, current) > 0;
}
