import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Badge } from "@/components/ui/Badge";

afterEach(cleanup);

describe("Badge contrast", () => {
  it("draws danger text in the lighter danger-text red", () => {
    render(<Badge variant="danger">2 critical</Badge>);
    const cls = screen.getByText("2 critical").className;
    expect(cls).toContain("text-danger-text");
    expect(cls).not.toMatch(/text-danger(?![\w-])/);
  });

  it("puts Void text on the prominent green fill, never white", () => {
    render(
      <Badge variant="success" prominent>
        Active
      </Badge>,
    );
    const cls = screen.getByText("Active").className;
    expect(cls).toContain("text-surface-0");
    expect(cls).not.toContain("text-white");
  });
});
