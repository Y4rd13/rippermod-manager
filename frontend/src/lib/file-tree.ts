import type { ArchiveEntryNode } from "@/types/api";

const SIZE_KEY = "\0size";

export function buildFileTree(
  files: { file_path: string; file_size: number }[],
): ArchiveEntryNode[] {
  const root: Record<string, unknown> = {};

  for (const f of files) {
    const parts = f.file_path.replace(/\\/g, "/").split("/").filter(Boolean);
    let node = root as Record<string, unknown>;
    for (const part of parts) {
      if (!(part in node)) node[part] = {};
      node = node[part] as Record<string, unknown>;
    }
    node[SIZE_KEY] = f.file_size;
  }

  function toTree(d: Record<string, unknown>): ArchiveEntryNode[] {
    const dirs: ArchiveEntryNode[] = [];
    const leaves: ArchiveEntryNode[] = [];
    for (const [name, value] of Object.entries(d)) {
      if (name === SIZE_KEY) continue;
      const child = value as Record<string, unknown>;
      const isDir = Object.keys(child).some((k) => k !== SIZE_KEY);
      if (isDir) {
        dirs.push({ name, is_dir: true, size: 0, children: toTree(child) });
      } else {
        leaves.push({
          name,
          is_dir: false,
          size: (child[SIZE_KEY] as number) ?? 0,
          children: [],
        });
      }
    }
    dirs.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
    leaves.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
    return [...dirs, ...leaves];
  }

  return toTree(root);
}
