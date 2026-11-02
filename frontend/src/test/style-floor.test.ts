/// <reference types="node" />
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(__dirname, "../index.css"), "utf8");
describe("fonts", () => {
  it("declares IBM Plex Sans and Mono", () => {
    expect(css).toMatch(/font-family:\s*"IBM Plex Sans"/);
    expect(css).toMatch(/font-family:\s*"IBM Plex Mono"/);
    expect(css).toMatch(/--font-sans:\s*"IBM Plex Sans", "Segoe UI", system-ui, sans-serif/);
    expect(css).toMatch(/--font-mono:\s*"IBM Plex Mono", Consolas, ui-monospace, monospace/);
  });
  it("never names Inter", () => expect(css).not.toMatch(/Inter/));
  it("ships the license next to the fonts", () =>
    expect(existsSync(resolve(__dirname, "../../public/fonts/ibm-plex/OFL.txt"))).toBe(true));
});
