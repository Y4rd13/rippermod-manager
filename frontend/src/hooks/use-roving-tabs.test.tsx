import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useRovingTabs } from "@/hooks/use-roving-tabs";

afterEach(cleanup);

const KEYS = ["a", "b", "c"] as const;
type K = (typeof KEYS)[number];

function Harness({ active, onSelect }: { active: K; onSelect: (k: K) => void }) {
  const { tabListProps, getTabProps } = useRovingTabs(KEYS, active, onSelect);
  return (
    <div {...tabListProps} aria-label="tabs">
      {KEYS.map((k) => (
        <button key={k} type="button" {...getTabProps(k)}>
          {k}
        </button>
      ))}
    </div>
  );
}

describe("useRovingTabs", () => {
  it("only the active tab is tabbable", () => {
    render(<Harness active="b" onSelect={() => {}} />);
    expect(screen.getAllByRole("tab").map((t) => t.tabIndex)).toEqual([-1, 0, -1]);
  });

  it("ArrowRight and ArrowLeft move focus and wrap", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<Harness active="c" onSelect={onSelect} />);
    screen.getByRole("tab", { name: "c" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "a" }));
    await user.keyboard("{ArrowLeft}");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "c" }));
    await user.keyboard("{ArrowLeft}");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "b" }));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("Home and End jump to the ends", async () => {
    const user = userEvent.setup();
    render(<Harness active="b" onSelect={() => {}} />);
    screen.getByRole("tab", { name: "b" }).focus();
    await user.keyboard("{End}");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "c" }));
    await user.keyboard("{Home}");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "a" }));
  });

  it("Enter selects the focused tab", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<Harness active="a" onSelect={onSelect} />);
    screen.getByRole("tab", { name: "a" }).focus();
    await user.keyboard("{ArrowLeft}");
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("c");
  });

  it("sets tab semantics", () => {
    render(<Harness active="a" onSelect={() => {}} />);
    expect(screen.getByRole("tablist")).toBeTruthy();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.getAttribute("aria-selected"))).toEqual(["true", "false", "false"]);
    expect(tabs.map((t) => t.getAttribute("aria-controls"))).toEqual([
      "tabpanel-a",
      "tabpanel-b",
      "tabpanel-c",
    ]);
  });
});
