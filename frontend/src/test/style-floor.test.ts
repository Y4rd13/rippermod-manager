/// <reference types="node" />
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(__dirname, "..");
const css = readFileSync(resolve(SRC, "index.css"), "utf8");

/** Every .ts/.tsx file under src/, test files excluded, with forward-slash paths. */
function sourceFiles(dir: string = SRC): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(full.replace(/\\/g, "/"));
  }
  return out;
}
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

describe("tokens", () => {
  it.each([
    ["--color-accent", "#5b5ee8"], ["--color-accent-hover", "#4f52dc"],
    ["--color-accent-text", "#818cf8"], ["--color-info", "#38bdf8"], ["--color-text-secondary", "#b8bdc9"],
  ])("%s is %s", (token, value) => expect(css).toContain(`${token}: ${value};`));
  it("uses accent-text for accent-coloured text", () => {
    const offenders = sourceFiles().filter((f) => /(?<![\w-])text-accent(?![\w-])/.test(readFileSync(f, "utf8")));
    expect(offenders).toEqual([]);
  });
});

describe("dialogs", () => {
  it("only Dialog renders aria-modal", () => {
    const offenders = sourceFiles().filter((f) => !f.endsWith("components/ui/Dialog.tsx") && readFileSync(f, "utf8").includes("aria-modal"));
    expect(offenders).toEqual([]);
  });
});

describe("text size", () => {
  it("has no text below 11px", () => {
    const offenders = sourceFiles().filter((f) => /text-\[(?:[0-9]|10)px\]/.test(readFileSync(f, "utf8")));
    expect(offenders).toEqual([]);
  });
});
