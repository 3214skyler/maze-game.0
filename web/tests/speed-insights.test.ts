import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const main = readFileSync(path.resolve(__dirname, "../src/main.ts"), "utf8");

describe("Vercel Speed Insights wiring", () => {
  it("uses the framework-agnostic package entry, never the Next.js one", () => {
    expect(main).toContain('from "@vercel/speed-insights"');
    expect(main).not.toMatch(/speed-insights\/next/);
  });
  it("only runs in production builds", () => {
    expect(main).toMatch(/if \(import\.meta\.env\.PROD\) injectSpeedInsights\(\)/);
  });
  it("is exported by the installed package", async () => {
    const mod = await import("@vercel/speed-insights");
    expect(typeof mod.injectSpeedInsights).toBe("function");
  });
});
