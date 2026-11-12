/** Where Back / Esc goes from each screen. Pure logic. */
export type Route = "menu" | "levels" | "play" | "daily" | "dailyplay" | "account";

const BACK: Record<Route, Route | null> = {
  menu: null,
  levels: "menu",
  play: "levels",
  daily: "menu",
  dailyplay: "daily",
  account: "menu",
};

export function backTarget(route: Route): Route | null {
  return BACK[route];
}

export interface ParsedRoute {
  route: Route;
  arg: number | null;
}

/** "#/play/3" -> { route: "play", arg: 3 }. Anything unknown or malformed falls back to the menu. */
export function parseHash(hash: string): ParsedRoute {
  const [name, rawArg] = hash.replace(/^#\/?/, "").split("/");
  const route = (name || "menu") as Route;
  if (!(route in BACK)) return { route: "menu", arg: null };
  if (route === "play") {
    const n = Number(rawArg);
    return Number.isInteger(n) && n >= 1 ? { route, arg: n } : { route: "levels", arg: null };
  }
  return { route, arg: null };
}

export const hashFor = (route: Route, arg?: number): string => (route === "menu" ? "#/" : `#/${route}${arg !== undefined ? `/${arg}` : ""}`);
