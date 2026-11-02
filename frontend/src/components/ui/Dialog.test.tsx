import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dialog } from "@/components/ui/Dialog";

afterEach(cleanup);

function Host({ children }: { children: ReactNode }) {
  return (
    <>
      <main data-inert-scope>
        <button type="button">behind</button>
      </main>
      {children}
    </>
  );
}

function TwoButtons({ onClose = () => {}, closeOnEscape }: { onClose?: () => void; closeOnEscape?: boolean }) {
  return (
    <Host>
      <Dialog onClose={onClose} titleId="t" closeOnEscape={closeOnEscape}>
        <h2 id="t">Title</h2>
        <button type="button">A</button>
        <button type="button">B</button>
      </Dialog>
    </Host>
  );
}

describe("Dialog", () => {
  it("focuses the first focusable control on open", () => {
    render(<TwoButtons />);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "A" }));
  });

  it("focuses the panel when it has no focusable child", () => {
    render(
      <Host>
        <Dialog onClose={() => {}} titleId="t">
          <h2 id="t">Working</h2>
          <p>Please wait</p>
        </Dialog>
      </Host>,
    );
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
  });

  it("keeps Tab inside the dialog", async () => {
    const user = userEvent.setup();
    render(<TwoButtons />);
    const a = screen.getByRole("button", { name: "A" });
    const b = screen.getByRole("button", { name: "B" });
    for (let i = 0; i < 3; i++) {
      await user.tab();
      expect([a, b]).toContain(document.activeElement);
    }
    await user.tab({ shift: true });
    expect([a, b]).toContain(document.activeElement);
  });

  it("closes on Escape unless closeOnEscape is false", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { unmount } = render(<TwoButtons onClose={onClose} />);
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    unmount();

    const blocked = vi.fn();
    render(<TwoButtons onClose={blocked} closeOnEscape={false} />);
    await user.keyboard("{Escape}");
    expect(blocked).not.toHaveBeenCalled();
  });

  it("returns focus to the opener on close", async () => {
    const user = userEvent.setup();
    function Opener() {
      const [open, setOpen] = useState(false);
      return (
        <Host>
          <button type="button" onClick={() => setOpen(true)}>
            open
          </button>
          <Dialog open={open} onClose={() => setOpen(false)} titleId="t">
            <h2 id="t">Title</h2>
            <button type="button" onClick={() => setOpen(false)}>
              close
            </button>
          </Dialog>
        </Host>
      );
    }
    render(<Opener />);
    const opener = screen.getByRole("button", { name: "open" });
    await user.click(opener);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "close" }));
    await user.click(screen.getByRole("button", { name: "close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("marks the inert scopes while open and clears them after", () => {
    function Toggle({ open }: { open: boolean }) {
      return (
        <Host>
          {open && (
            <Dialog onClose={() => {}} titleId="t">
              <h2 id="t">Title</h2>
            </Dialog>
          )}
        </Host>
      );
    }
    const { rerender } = render(<Toggle open />);
    const main = document.querySelector("main")!;
    expect(main.hasAttribute("inert")).toBe(true);
    rerender(<Toggle open={false} />);
    expect(document.querySelector("main")).toBe(main);
    expect(main.hasAttribute("inert")).toBe(false);
  });

  it("only the top dialog of a stack is active", async () => {
    const user = userEvent.setup();
    const lowerClose = vi.fn();
    const topClose = vi.fn();
    render(
      <Host>
        <Dialog onClose={lowerClose} titleId="low">
          <h2 id="low">Lower</h2>
          <button type="button">lower button</button>
          <Dialog onClose={topClose} titleId="top">
            <h2 id="top">Top</h2>
            <button type="button">top button</button>
          </Dialog>
        </Dialog>
      </Host>,
    );
    const lower = screen.getByRole("dialog", { name: "Lower", hidden: true });
    const top = screen.getByRole("dialog", { name: "Top", hidden: true });
    expect(lower.hasAttribute("inert")).toBe(true);
    expect(top.hasAttribute("inert")).toBe(false);
    await user.keyboard("{Escape}");
    expect(topClose).toHaveBeenCalledTimes(1);
    expect(lowerClose).not.toHaveBeenCalled();
  });

  it("renders role=dialog with aria-modal and aria-labelledby", () => {
    render(<TwoButtons />);
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-labelledby")).toBe("t");
  });
});
