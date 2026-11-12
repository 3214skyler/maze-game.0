import { describe, expect, it } from "vitest";
import { backTarget, hashFor, parseHash, Route } from "../src/ui/navigation";

describe("navigation", () => {
  it("parses hashes and falls back safely", () => {
    expect(parseHash("")).toEqual({ route: "menu", arg: null });
    expect(parseHash("#/")).toEqual({ route: "menu", arg: null });
    expect(parseHash("#/levels")).toEqual({ route: "levels", arg: null });
    expect(parseHash("#/play/7")).toEqual({ route: "play", arg: 7 });
    expect(parseHash("#/daily")).toEqual({ route: "daily", arg: null });
    expect(parseHash("#/dailyplay")).toEqual({ route: "dailyplay", arg: null });
    expect(parseHash("#/nonsense")).toEqual({ route: "menu", arg: null });
    for (const bad of ["#/play", "#/play/abc", "#/play/0", "#/play/-3", "#/play/1.5"]) {
      expect(parseHash(bad)).toEqual({ route: "levels", arg: null });
    }
  });

  it("hashFor and parseHash agree", () => {
    expect(hashFor("menu")).toBe("#/");
    expect(parseHash(hashFor("play", 12))).toEqual({ route: "play", arg: 12 });
    for (const r of ["levels", "daily", "dailyplay", "account"] as Route[]) expect(parseHash(hashFor(r)).route).toBe(r);
  });

  it("Back/Esc always leads towards the menu, which is the end of the line", () => {
    expect(backTarget("menu")).toBeNull();
    for (const r of ["levels", "play", "daily", "dailyplay", "account"] as Route[]) {
      let cur: Route | null = r;
      let steps = 0;
      while (cur && steps < 10) { cur = backTarget(cur); steps++; }
      expect(cur).toBeNull();
      expect(steps).toBeLessThan(10);
    }
    expect(backTarget("play")).toBe("levels");
    expect(backTarget("dailyplay")).toBe("daily");
  });
});
