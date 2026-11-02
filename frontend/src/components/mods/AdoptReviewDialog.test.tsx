import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdoptReviewDialog } from "@/components/mods/AdoptReviewDialog";
import type { CorrelationBrief, ModGroup } from "@/types/api";

vi.mock("@/hooks/mutations", () => ({
  useAdoptMods: () => ({ mutate: vi.fn(), isPending: false }),
}));

afterEach(cleanup);

function match(score: number, onDisk: boolean | undefined): CorrelationBrief {
  const m = {
    nexus_mod_id: 1000 + Math.round(score * 100),
    mod_name: `Nexus ${score}`,
    score,
    method: "fuzzy",
    confirmed: false,
    author: "",
    summary: "",
    version: "1.0",
    endorsement_count: 0,
    category: "",
    picture_url: "",
    nexus_url: "",
    updated_at: null,
    on_disk: onDisk,
    is_endorsed: false,
    is_tracked: false,
  };
  if (onDisk === undefined) delete (m as Partial<typeof m>).on_disk;
  return m as CorrelationBrief;
}

function group(id: number, name: string, score: number, onDisk: boolean | undefined): ModGroup {
  return {
    id,
    game_id: 1,
    display_name: name,
    confidence: 1,
    files: [{ id, file_path: `archive/pc/mod/${name}.archive`, filename: `${name}.archive`, file_hash: "", file_size: 1, source_folder: "archive/pc/mod" }],
    nexus_match: match(score, onDisk),
    earliest_file_mtime: null,
  };
}

const MODS: ModGroup[] = [
  group(1, "Alpha", 0.95, true),
  group(2, "Bravo", 0.92, true),
  group(3, "Charlie", 0.97, true),
  group(4, "Delta", 0.56, false),
  group(5, "Echo", 0.8, false),
  group(6, "Foxtrot", 0.7, undefined),
];

function renderDialog(mods: ModGroup[], preselectIds: number[]) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <AdoptReviewDialog gameName="Cyberpunk 2077" mods={mods} preselectIds={preselectIds} onClose={() => {}} />
    </QueryClientProvider>,
  );
}

const checkbox = (name: string) => screen.getByRole("checkbox", { name: `Adopt ${name}` }) as HTMLInputElement;

describe("AdoptReviewDialog", () => {
  it("preselects exactly preselectIds", async () => {
    const user = userEvent.setup();
    renderDialog(MODS, [1, 2, 3]);
    expect(screen.getByRole("button", { name: /^Adopt 3 mods/ })).toBeTruthy();
    expect(checkbox("Alpha").checked).toBe(true);
    await user.click(screen.getByRole("button", { name: /Possible matches/ }));
    expect(checkbox("Delta").checked).toBe(false);
    expect(checkbox("Echo").checked).toBe(false);
  });

  it("collapses possible matches by default", () => {
    renderDialog(MODS, [1, 2, 3]);
    const toggle = screen.getByRole("button", { name: /Possible matches \(3\)/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });

  it("treats a missing on_disk as not on disk", () => {
    renderDialog(MODS, [1, 2, 3]);
    const detected = screen.getByRole("region", { name: /Detected on disk/ });
    expect(detected.textContent).not.toContain("Foxtrot");
    expect(screen.getByRole("button", { name: /Possible matches \(3\)/ })).toBeTruthy();
  });

  it("expands possible matches when a preselected row is there", () => {
    renderDialog(MODS, [4]);
    const toggle = screen.getByRole("button", { name: /Possible matches \(3\)/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(checkbox("Delta").checked).toBe(true);
    expect(screen.getByText("56%")).toBeTruthy();
  });

  it("disables confirm with nothing selected", () => {
    renderDialog(MODS.slice(3), []);
    const confirm = screen.getByRole("button", { name: "Select mods to adopt" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    const toggle = screen.getByRole("button", { name: /Possible matches \(3\)/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
  });
});
