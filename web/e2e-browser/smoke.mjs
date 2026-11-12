/**
 * Real-browser smoke test (headless Chromium): builds the web game against a fake Supabase (real PostgreSQL behind it),
 * serves it with the production Content-Security-Policy, and plays it with real mouse/touch/keyboard input.
 *
 *   cd web/e2e-browser && npm install && npm run e2e
 * Needs: python3 + a local PostgreSQL (same as the Python backend tests).
 */
import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import chromium from "@sparticuz/chromium";
import { build } from "esbuild";
import puppeteer from "puppeteer-core";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WEB = path.resolve(HERE, "..");
const ROOT = path.resolve(WEB, "..");
const SHOTS = path.join(ROOT, "docs", "screenshots");
fs.mkdirSync(SHOTS, { recursive: true });

const failures = [];
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : `  -> ${detail}`}`);
  if (!ok) failures.push(name);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------- 1. fake Supabase (real PostgreSQL)
const py = spawn("python3", [path.join(ROOT, "tests", "http_fake_supabase.py")], { cwd: ROOT, stdio: ["ignore", "pipe", "inherit"] });
const supaPort = await new Promise((resolve, reject) => {
  const t = setTimeout(() => reject(new Error("fake Supabase did not start")), 20000);
  py.stdout.on("data", (d) => { const m = /PORT=(\d+)/.exec(d.toString()); if (m) { clearTimeout(t); resolve(Number(m[1])); } });
  py.on("exit", () => reject(new Error("fake Supabase exited (python3/PostgreSQL available?)")));
});
const SUPA = `http://127.0.0.1:${supaPort}`;
const control = (name, body = {}) => fetch(`${SUPA}/__test__/${name}`, { method: "POST", body: JSON.stringify(body) });

// ---------------------------------------------------------------- 2. production build pointed at the fake backend
execFileSync(path.join(WEB, "node_modules", ".bin", "vite"), ["build", "--outDir", "dist-e2e", "--emptyOutDir"], {
  cwd: WEB, stdio: "pipe", env: { ...process.env, VITE_SUPABASE_URL: SUPA, VITE_SUPABASE_ANON_KEY: "anon-test-key" },
});

// ---------------------------------------------------------------- 3. game logic bundle (to compute solutions in Node)
await build({
  stdin: {
    contents: `export * from "./src/core/solver.ts"; export * from "./src/core/maze.ts";
               export { layoutFor } from "./src/ui/render.ts"; export { buildLevel } from "./src/game/levels.ts";`,
    resolveDir: WEB, loader: "ts",
  },
  bundle: true, format: "esm", platform: "node", outfile: path.join(HERE, ".core.mjs"), logLevel: "silent",
});
const core = await import(path.join(HERE, ".core.mjs"));

// ---------------------------------------------------------------- 4. static server with the PRODUCTION CSP
const vercel = JSON.parse(fs.readFileSync(path.join(WEB, "vercel.json"), "utf8"));
const csp = vercel.headers[0].headers.find((h) => h.key === "Content-Security-Policy").value
  .replace("https://*.supabase.co", `https://*.supabase.co ${SUPA}`);
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml" };
const dist = path.join(WEB, "dist-e2e");
let speedInsightsHits = [];
const server = http.createServer((req, res) => {
  let p = decodeURIComponent((req.url || "/").split("?")[0]);
  if (p.startsWith("/_vercel/speed-insights/")) {           // what Vercel serves in production (stubbed here)
    speedInsightsHits.push(p);
    res.writeHead(p.endsWith("script.js") ? 200 : 204, { "Content-Type": "text/javascript", "Content-Security-Policy": csp });
    return res.end(p.endsWith("script.js") ? "/* speed insights stub */" : "");
  }
  if (p === "/") p = "/index.html";
  const file = path.join(dist, path.normalize(p));
  if (!file.startsWith(dist) || !fs.existsSync(file)) { res.writeHead(404); return res.end("not found"); }
  res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream", "Content-Security-Policy": csp, "X-Content-Type-Options": "nosniff" });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const APP = `http://127.0.0.1:${server.address().port}`;

// ---------------------------------------------------------------- 5. browser
// the packaged Chromium targets AWS Lambda: --single-process/--no-zygote would forbid separate browser contexts
const launchArgs = chromium.args.filter((a) => !["--single-process", "--no-zygote"].includes(a));
const browser = await puppeteer.launch({ args: [...launchArgs, "--no-sandbox"], executablePath: await chromium.executablePath(), headless: "shell" });

async function newPage({ mobile = false } = {}) {
  const context = await browser.createBrowserContext(); // clean localStorage per scenario
  const page = await context.newPage();
  await page.setViewport(mobile ? { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true } : { width: 480, height: 820 });
  const errors = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("requestfailed", (r) => errors.push(`request failed: ${r.url()} ${r.failure()?.errorText}`));
  return { page, errors, context };
}
const clickText = (page, text) => page.evaluate((t) => {
  const b = [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === t && !x.disabled);
  if (!b) return false;
  b.click();
  return true;
}, text);
const bodyText = (page) => page.evaluate(() => document.body.innerText);
const waitText = async (page, text, ms = 8000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if ((await bodyText(page)).includes(text)) return true; await sleep(100); }
  return false;
};

async function boardGeometry(page) {
  await page.waitForSelector("canvas.board");
  await sleep(150);
  return page.$eval("canvas.board", (c) => { const r = c.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
}
const cellPoint = (rect, vp, c) => [rect.x + vp.originX + (c[0] + 0.5) * vp.cellSize, rect.y + vp.originY + (c[1] + 0.5) * vp.cellSize];

async function drawWithMouse(page, maze, route) {
  const rect = await boardGeometry(page);
  const vp = core.layoutFor(rect.w, rect.h, maze);
  await page.mouse.move(...cellPoint(rect, vp, route[0]));
  await page.mouse.down();
  for (const c of route.slice(1)) await page.mouse.move(...cellPoint(rect, vp, c), { steps: 2 });
  await page.mouse.up();
}

async function drawWithTouch(page, maze, route) {
  const rect = await boardGeometry(page);
  const vp = core.layoutFor(rect.w, rect.h, maze);
  const [sx, sy] = cellPoint(rect, vp, route[0]);
  const touch = await page.touchscreen.touchStart(sx, sy);
  for (const c of route.slice(1)) { const [x, y] = cellPoint(rect, vp, c); await touch.move(x, y); }
  await touch.end();
}

// ================================================================ A. guest: menu, levels, play level 1 with the mouse
{
  const { page, errors, context } = await newPage();
  await page.goto(APP, { waitUntil: "networkidle0" });
  const menu = await bodyText(page);
  check("menu renders with the three buttons", ["MAZE GAME", "PLAY", "DAILY CHALLENGE", "ACCOUNT", "Playing as guest"].every((t) => menu.includes(t)), menu);
  await page.screenshot({ path: path.join(SHOTS, "web-menu.png") });

  await clickText(page, "PLAY");
  await page.waitForSelector(".levels");
  const state = await page.$$eval(".levels button", (bs) => bs.map((b) => !b.disabled));
  check("only level 1 is unlocked at first (100 levels)", state.length === 100 && state[0] === true && state.slice(1).every((x) => !x), JSON.stringify(state.slice(0, 4)));

  await clickText(page, "1");
  const maze1 = core.buildLevel(1);
  const route1 = core.solve(maze1);
  await drawWithMouse(page, maze1, route1);
  check("drawing the solution with the mouse clears the level", await waitText(page, "LEVEL CLEARED"), await bodyText(page));
  const progress = JSON.parse(await page.evaluate(() => localStorage.getItem("maze.progress.v1")));
  check("progress is saved: level 2 unlocked, best time stored", progress.highest === 2 && progress.best["1"] > 0, JSON.stringify(progress));
  check("victory panel offers next level and shows unlock", (await bodyText(page)).includes("LEVEL 2 UNLOCKED") && (await bodyText(page)).includes("NEXT LEVEL"));
  await page.screenshot({ path: path.join(SHOTS, "web-victory.png") });

  await clickText(page, "NEXT LEVEL");
  await page.waitForSelector("canvas.board");
  check("NEXT LEVEL opens level 2", page.url().endsWith("#/play/2"), page.url());

  await page.reload({ waitUntil: "networkidle0" });                 // "reopen the browser"
  await page.evaluate(() => (location.hash = "#/levels"));
  await page.waitForSelector(".levels");
  const after = await page.$$eval(".levels button", (bs) => bs.map((b) => !b.disabled));
  check("progress survives a reload", after[0] && after[1] && !after[2], JSON.stringify(after.slice(0, 4)));

  await page.evaluate(() => (location.hash = "#/play/5"));          // cannot skip ahead by editing the URL
  await sleep(300);
  check("a locked level cannot be opened through the URL", page.url().endsWith("#/levels"), page.url());
  const si = await page.evaluate(() => !!document.head.querySelector('script[src="/_vercel/speed-insights/script.js"]'));
  check("Speed Insights script is injected and allowed by the production CSP", si && speedInsightsHits.includes("/_vercel/speed-insights/script.js"), JSON.stringify(speedInsightsHits));
  check("no console errors or CSP violations (guest flow)", errors.length === 0, errors.join(" | "));
  await context.close();
}

// ================================================================ B. mobile: touch drawing + keyboard + three colours
{
  const { page, errors, context } = await newPage({ mobile: true });
  await page.goto(`${APP}/#/play/1`, { waitUntil: "networkidle0" });
  const maze1 = core.buildLevel(1);
  const route = core.solve(maze1);
  await page.waitForSelector("canvas.board");
  // keep the player on level 1 (locked levels redirect): draw partially with a finger, then switch colour and reset
  await drawWithTouch(page, maze1, route.slice(0, 5));
  await clickText(page, "GREEN");
  const bar = await page.$$eval(".colours button", (bs) => bs.map((b) => [b.textContent.trim(), b.classList.contains("dim")]));
  check("colour buttons show the active colour", bar[1][1] === false && bar[0][1] === true && bar[2][1] === true, JSON.stringify(bar));
  await page.screenshot({ path: path.join(SHOTS, "web-mobile-play.png") });
  await clickText(page, "BLUE");
  await drawWithTouch(page, maze1, route.slice(4));
  check("a finger can finish the path (touch input)", await waitText(page, "LEVEL CLEARED"), await bodyText(page));
  check("no console errors (mobile flow)", errors.length === 0, errors.join(" | "));
  await context.close();
}

// ================================================================ C. keyboard: arrows move the active path
{
  const { page, errors, context } = await newPage();
  await page.goto(`${APP}/#/play/1`, { waitUntil: "networkidle0" });
  const maze1 = core.buildLevel(1);
  const route = core.solve(maze1);
  const dirKey = (a, b) => (b[0] > a[0] ? "ArrowRight" : b[0] < a[0] ? "ArrowLeft" : b[1] > a[1] ? "ArrowDown" : "ArrowUp");
  for (let i = 1; i < route.length; i++) await page.keyboard.press(dirKey(route[i - 1], route[i]));
  check("arrow keys can solve the level", await waitText(page, "LEVEL CLEARED"), await bodyText(page));
  check("no console errors (keyboard flow)", errors.length === 0, errors.join(" | "));
  await context.close();
}

// ================================================================ D. account + daily challenge against the real SQL
{
  await control("reset");
  await control("publish");
  const { page, errors, context } = await newPage();
  let startBody = null;
  page.on("response", async (res) => { if (res.url().includes("/rpc/start_daily_run") && res.ok()) startBody = await res.json(); });

  await page.goto(`${APP}/#/account`, { waitUntil: "networkidle0" });
  const typeInto = async (placeholder, value) => { const el = await page.$(`input[placeholder^="${placeholder}"]`); await el.click({ clickCount: 3 }); await el.type(value); };
  await clickText(page, "CREATE ACCOUNT");
  check("empty form is rejected client-side with a clear message", (await bodyText(page)).includes("valid e-mail"));
  await typeInto("e-mail", "browser@test.dev");
  await typeInto("password", "secret12");
  await typeInto("username", "browser_player");
  await clickText(page, "CREATE ACCOUNT");
  check("account creation works over real CORS + CSP", await waitText(page, "Signed in as browser_player"), await bodyText(page));
  await page.screenshot({ path: path.join(SHOTS, "web-account.png") });

  await page.evaluate(() => (location.hash = "#/daily"));
  check("daily screen shows an empty board and an enabled PLAY button", await waitText(page, "No times yet today"));
  const playEnabled = await page.evaluate(() => [...document.querySelectorAll("button")].some((b) => b.textContent.includes("PLAY TODAY") && !b.disabled));
  check("PLAY is enabled once signed in", playEnabled);

  await clickText(page, "PLAY TODAY'S MAZE");
  const t0 = Date.now();
  while (!startBody && Date.now() - t0 < 8000) await sleep(100);
  check("the server handed out the daily maze", !!startBody && Array.isArray(startBody.walls), JSON.stringify(startBody)?.slice(0, 80));
  const dailyMaze = core.Maze.fromJSON(startBody);
  const route = core.solve(dailyMaze);
  await control("age_run", { run_id: startBody.run_id, seconds: route.length * 0.08 + 12 }); // the server measures the time
  await drawWithMouse(page, dailyMaze, route);
  check("the run is accepted and ranked #1", await waitText(page, "RANK #1"), await bodyText(page));
  await page.screenshot({ path: path.join(SHOTS, "web-daily-result.png") });

  await clickText(page, "LEADERBOARD");
  check("the leaderboard lists the player", await waitText(page, "browser_player"), await bodyText(page));
  await page.screenshot({ path: path.join(SHOTS, "web-daily.png") });

  await page.reload({ waitUntil: "networkidle0" });
  check("the session survives a page reload", (await bodyText(page)).includes("browser_player") || (await waitText(page, "browser_player")));

  // a cheating attempt: scripted instant submission must be refused by the server
  await clickText(page, "PLAY AGAIN") || await page.evaluate(() => (location.hash = "#/dailyplay"));
  startBody = null;
  await page.evaluate(() => (location.hash = "#/daily"));
  await waitText(page, "PLAY TODAY");
  await clickText(page, "PLAY TODAY'S MAZE");
  const t1 = Date.now();
  while (!startBody && Date.now() - t1 < 8000) await sleep(100);
  const m2 = core.Maze.fromJSON(startBody);
  await drawWithMouse(page, m2, core.solve(m2));                    // perfect path, but instantly
  check("an instant (scripted-looking) run is rejected by the server", await waitText(page, "quickly"), await bodyText(page));

  check("no console errors or CSP violations (account + daily flow)", errors.length === 0, errors.join(" | "));
  await context.close();
}

// ================================================================ E. offline-tolerant: the game works without a network
{
  const { page, context } = await newPage();
  await page.goto(`${APP}/#/daily`, { waitUntil: "networkidle0" });
  await control("offline", { offline: true });
  await page.evaluate(() => (location.hash = "#/account"));
  const typeInto = async (placeholder, value) => { const el = await page.$(`input[placeholder^="${placeholder}"]`); await el.click({ clickCount: 3 }); await el.type(value); };
  await typeInto("e-mail", "offline@test.dev"); await typeInto("password", "secret12");
  await clickText(page, "SIGN IN");
  check("a dead connection shows a friendly message, not a crash", await waitText(page, "No connection"), await bodyText(page));
  await control("offline", { offline: false });
  await page.evaluate(() => (location.hash = "#/play/1"));
  await page.waitForSelector("canvas.board");
  check("classic levels still work while the backend is down", true);
  await context.close();
}

await browser.close();
server.close();
py.kill();
fs.rmSync(dist, { recursive: true, force: true });
fs.rmSync(path.join(HERE, ".core.mjs"), { force: true });
console.log(failures.length ? `\n${failures.length} FAILED: ${failures.join("; ")}` : "\nAll browser checks passed.");
process.exit(failures.length ? 1 : 0);
