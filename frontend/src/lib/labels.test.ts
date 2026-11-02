import { describe, expect, it, vi } from "vitest";
import { activityLabel, matchMethodLabel } from "@/lib/labels";

describe("matchMethodLabel", () => {
  it.each([
    ["filename_id", "Filename ID"], ["exact", "Exact name"], ["substring", "Name contains"],
    ["fuzzy", "Name similarity"], ["file_content", "File contents"], ["file_list", "File list"],
    ["endorsed_name", "Endorsed (name)"], ["requirement", "Requirement of another mod"],
    ["collection", "Collection"], ["manual", "Set by you"], ["installed", "Installed"], ["fomod", "FOMOD"],
  ])("labels %s as %s", (method, label) => expect(matchMethodLabel(method)).toBe(label));
  it("title-cases an unknown method", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(matchMethodLabel("web_search_v2")).toBe("Web Search V2");
    matchMethodLabel("web_search_v2");
    expect(warn).toHaveBeenCalledTimes(1);
  });
  it("labels an empty method as Unknown", () => {
    expect(matchMethodLabel("")).toBe("Unknown");
    expect(matchMethodLabel(undefined)).toBe("Unknown");
  });
});
describe("activityLabel", () => {
  it("labels adopt as Adopted", () => expect(activityLabel("adopt")).toBe("Adopted"));
  it("keeps the existing labels", () => expect(activityLabel("undo")).toBe("Undid"));
});
