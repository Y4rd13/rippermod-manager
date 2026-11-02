import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

afterEach(cleanup);

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <main data-inert-scope>
        <button type="button" onClick={() => setOpen(true)}>
          open
        </button>
        <button type="button">behind</button>
      </main>
      {open && (
        <ConfirmDialog
          title="Delete it?"
          message="This cannot be undone."
          onConfirm={() => setOpen(false)}
          onCancel={() => setOpen(false)}
        />
      )}
    </>
  );
}

describe("ConfirmDialog", () => {
  it("traps focus and restores it to the opener", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "open" });
    await user.click(opener);
    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Confirm" });
    for (let i = 0; i < 5; i++) {
      await user.tab();
      expect([cancel, confirm]).toContain(document.activeElement);
    }
    await user.click(cancel);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("does not close on Escape while loading", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog title="Busy" message="Working" loading onConfirm={() => {}} onCancel={onCancel} />,
    );
    await user.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
  });
});
