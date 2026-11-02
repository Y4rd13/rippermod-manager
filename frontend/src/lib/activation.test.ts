import type { KeyboardEvent } from "react";
import { describe, expect, it, vi } from "vitest";

import { activationProps } from "@/lib/activation";

function keyEvent(key: string, self = true) {
  const target = {};
  return {
    key,
    target,
    currentTarget: self ? target : {},
    preventDefault: vi.fn(),
  } as unknown as KeyboardEvent & { preventDefault: ReturnType<typeof vi.fn> };
}

describe("activationProps", () => {
  it("activates on Enter and Space", () => {
    const onActivate = vi.fn();
    const props = activationProps(onActivate);
    props.onKeyDown(keyEvent("Enter"));
    props.onKeyDown(keyEvent(" "));
    props.onKeyDown(keyEvent("a"));
    expect(onActivate).toHaveBeenCalledTimes(2);
    expect(props.tabIndex).toBe(0);
  });

  it("ignores keys from inner controls", () => {
    const onActivate = vi.fn();
    activationProps(onActivate).onKeyDown(keyEvent("Enter", false));
    expect(onActivate).not.toHaveBeenCalled();
  });

  it("prevents page scroll on Space", () => {
    const e = keyEvent(" ");
    activationProps(() => {}).onKeyDown(e);
    expect(e.preventDefault).toHaveBeenCalled();
  });
});
