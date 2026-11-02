import { describe, expect, it } from "vitest";
import { plural } from "@/lib/format";

describe("plural", () => {
  it("uses the singular for one", () => expect(plural(1, "file")).toBe("1 file"));
  it("adds s by default", () => expect(plural(3, "file")).toBe("3 files"));
  it("uses the plural for zero", () => expect(plural(0, "file")).toBe("0 files"));
  it("takes an explicit plural form", () => expect(plural(2, "match", "matches")).toBe("2 matches"));
});
