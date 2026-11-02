import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ModCardAction } from "@/components/mods/ModCardAction";
import type { DownloadJobOut } from "@/types/api";

afterEach(cleanup);

const completed: DownloadJobOut = {
  id: 1,
  nexus_mod_id: 10,
  nexus_file_id: 20,
  file_name: "mod-10-1-0.zip",
  status: "completed",
  progress_bytes: 100,
  total_bytes: 100,
  percent: 100,
  error: "",
  created_at: "2026-11-02T00:00:00Z",
  completed_at: "2026-11-02T00:01:00Z",
};

const noop = () => {};

describe("ModCardAction", () => {
  it("renders Install Update with black text on amber", () => {
    render(
      <ModCardAction
        isInstalled={false}
        isInstalling={false}
        completedDownload={completed}
        hasConflicts={false}
        isDownloading={false}
        isUpdate
        onInstall={noop}
        onInstallByFilename={noop}
        onDownload={noop}
        onCancelDownload={noop}
      />,
    );
    const button = screen.getByRole("button", { name: /Install Update/ });
    expect(button.className).toContain("text-black");
    expect(button.className).not.toContain("text-white");
  });
});
