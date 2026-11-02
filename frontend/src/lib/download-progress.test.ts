import { describe, expect, it } from "vitest";

import { summarizeDownloads } from "@/lib/download-progress";

describe("summarizeDownloads", () => {
  it("averages only downloading jobs", () =>
    expect(
      summarizeDownloads([
        { status: "downloading", percent: 50 },
        { status: "downloading", percent: 100 },
        { status: "queued", percent: 0 },
      ]),
    ).toEqual({ downloadingPercent: 75, queued: 1, active: 3 }));

  it("reports queued jobs without averaging them", () =>
    expect(
      summarizeDownloads([
        { status: "queued", percent: 0 },
        { status: "pending", percent: 0 },
      ]),
    ).toEqual({ downloadingPercent: null, queued: 2, active: 2 }));

  it("ignores terminal jobs", () =>
    expect(summarizeDownloads([{ status: "completed", percent: 100 }])).toEqual({
      downloadingPercent: null,
      queued: 0,
      active: 0,
    }));
});
