import { describe, expect, it } from "vitest";

import { countTrustedMatches } from "@/lib/matches";

type Mod = Parameters<typeof countTrustedMatches>[0][number];

const mod = (nexus_match: { on_disk: boolean } | null) => ({ nexus_match }) as unknown as Mod;

describe("countTrustedMatches", () => {
  it("counts only matches the backend marks on_disk (confirmed or score >= 0.75)", () => {
    const mods = [mod({ on_disk: true }), mod({ on_disk: false }), mod(null), mod({ on_disk: true })];
    expect(countTrustedMatches(mods)).toBe(2);
  });

  it("is 0 for no mods", () => {
    expect(countTrustedMatches([])).toBe(0);
  });
});
