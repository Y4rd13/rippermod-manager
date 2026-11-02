import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Boxes, HeartPulse, Link2, Package, RefreshCw, AlertTriangle, UserCheck } from "lucide-react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GameStatusStrip, type StatusItem } from "@/components/GameStatusStrip";

afterEach(cleanup);

function items(overrides: Partial<Record<StatusItem["key"], Partial<StatusItem>>> = {}): StatusItem[] {
  const base: StatusItem[] = [
    { key: "scanned", label: "Scanned", value: "187", icon: Package, onSelect: () => {} },
    { key: "managed", label: "Managed", value: "120/122", icon: UserCheck, onSelect: () => {} },
    { key: "matched", label: "Nexus Matched", value: "190", icon: Link2, onSelect: () => {} },
    { key: "updates", label: "Updates", value: "92", tone: "warning", icon: RefreshCw, onSelect: () => {} },
    { key: "conflicts", label: "Conflicts", value: "2", tone: "warning", icon: AlertTriangle, onSelect: () => {} },
    { key: "frameworks", label: "Frameworks", value: "All OK", tone: "success", icon: Boxes, onSelect: () => {} },
    { key: "health", label: "Health", value: "2 critical", tone: "danger", icon: HeartPulse, onSelect: () => {} },
  ];
  return base.map((i) => ({ ...i, ...overrides[i.key] }));
}

describe("GameStatusStrip", () => {
  it("renders one button per item in order", () => {
    render(<GameStatusStrip items={items()} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(7);
    expect(buttons.map((b) => b.textContent)).toEqual([
      "187Scanned",
      "120/122Managed",
      "190Nexus Matched",
      "92Updates",
      "2Conflicts",
      "All OKFrameworks",
      "2 criticalHealth",
    ]);
  });

  it("calls onSelect on click and on Enter", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<GameStatusStrip items={items({ updates: { onSelect } })} />);
    const updates = screen.getByRole("button", { name: /Updates/ });
    await user.click(updates);
    updates.focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it("gives every icon shrink-0", () => {
    const { container } = render(<GameStatusStrip items={items()} />);
    const icons = [...container.querySelectorAll("svg")];
    expect(icons).toHaveLength(7);
    for (const svg of icons) expect(svg.classList.contains("shrink-0")).toBe(true);
  });

  it("marks tone with a text colour class", () => {
    render(<GameStatusStrip items={items()} />);
    expect(screen.getByText("2 critical").className).toContain("text-danger");
    expect(screen.getByText("187").className).not.toMatch(/text-(danger|warning|success)/);
  });
});
