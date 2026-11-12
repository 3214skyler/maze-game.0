import "./styles.css";
import { injectSpeedInsights } from "@vercel/speed-insights"; // framework-agnostic entry point (NOT ".../next": this is not a Next.js app)
import { ProgressStore } from "./game/progress";
import { Account } from "./net/account";
import { StorageLike } from "./net/auth";
import { configFromEnv } from "./net/config";
import { DailyClient } from "./net/daily";
import { HttpClient } from "./net/http";
import { clear } from "./ui/dom";
import { backTarget, hashFor, parseHash, Route } from "./ui/navigation";
import { accountScreen, Cleanup, Ctx, dailyPlayScreen, dailyScreen, levelsScreen, menuScreen, playScreen } from "./ui/screens";

/** localStorage can throw (blocked cookies / private mode): fall back to memory so the game still runs. */
function safeStorage(): StorageLike {
  try {
    const probe = "__maze_probe__";
    localStorage.setItem(probe, "1");
    localStorage.removeItem(probe);
    return localStorage;
  } catch {
    const m = new Map<string, string>();
    return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v), removeItem: (k) => void m.delete(k) };
  }
}

const root = document.getElementById("app") as HTMLElement;
const storage = safeStorage();
let cfg = null;
try {
  cfg = configFromEnv();
} catch (e) {
  console.error(e); // bad URL in the build settings: run as an offline-only build
}
const account = cfg ? new Account(cfg, storage, new HttpClient()) : null;
const lowPower = (navigator.hardwareConcurrency ?? 4) <= 2 || matchMedia("(prefers-reduced-motion: reduce)").matches;

let cleanup: Cleanup = () => {};

function render(): void {
  cleanup();
  clear(root);
  const { route, arg } = parseHash(location.hash);
  const screens: Record<Route, () => Cleanup> = {
    menu: () => menuScreen(ctx, root),
    levels: () => levelsScreen(ctx, root),
    play: () => playScreen(ctx, root, arg ?? 1),
    daily: () => dailyScreen(ctx, root),
    dailyplay: () => dailyPlayScreen(ctx, root),
    account: () => accountScreen(ctx, root),
  };
  cleanup = screens[route]();
}

const ctx: Ctx = {
  account,
  daily: account ? new DailyClient(account.api) : null,
  progress: new ProgressStore(storage),
  glow: !lowPower,
  go(route, arg) {
    const target = hashFor(route, arg);
    if (location.hash === target || (route === "menu" && (location.hash === "" || location.hash === "#"))) render();
    else location.hash = target;
  },
};

window.addEventListener("hashchange", render);
window.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const target = backTarget(parseHash(location.hash).route);
  if (target) ctx.go(target);
});

render();
if (account?.signedIn) {
  // learn the username of a returning player, then refresh the menu if it is still showing
  void account.refreshProfile().then(() => parseHash(location.hash).route === "menu" && render(), () => {});
}

// Vercel Speed Insights: real-user Web Vitals. Production only; the script is served by Vercel from this same
// origin (/_vercel/speed-insights/...), so the Content-Security-Policy needs no change. Enable it in the Vercel dashboard.
if (import.meta.env.PROD) injectSpeedInsights();
