import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NexusModTile } from "@/components/mods/NexusModTile";

afterEach(cleanup);

describe("NexusModTile", () => {
  it("opens from the keyboard like the card and row views", () => {
    const onClick = vi.fn();
    render(<NexusModTile modName="Alpha" onClick={onClick} />);
    const tile = screen.getByRole("img", { name: "Alpha" }).closest("div.relative.flex") as HTMLElement;
    expect(tile.tabIndex).toBe(0);
    fireEvent.keyDown(tile, { key: "Enter" });
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
