/** All screens. Each one renders into `root` and returns a cleanup function. */
import { MazeFormatError } from "../core/maze";
import { PATH_COLORS, PathColor } from "../core/paths";
import { buildLevel, MAX_LEVEL } from "../game/levels";
import { ProgressStore } from "../game/progress";
import { Account, USERNAME_RE } from "../net/account";
import { DailyClient, DailyRun, fmtMs, friendly } from "../net/daily";
import { AuthError, NetworkError, ServerError } from "../net/errors";
import { GameBoard } from "./board";
import { h } from "./dom";
import { Route } from "./navigation";

export interface Ctx {
  account: Account | null;
  daily: DailyClient | null;
  progress: ProgressStore;
  glow: boolean;
  go: (route: Route, arg?: number) => void;
}
export type Cleanup = () => void;
const none: Cleanup = () => {};

export function errorText(e: unknown): string {
  if (e instanceof ServerError) return friendly(e);
  if (e instanceof NetworkError) return "No connection. Check your internet and try again.";
  if (e instanceof AuthError) return e.message;
  if (e instanceof MazeFormatError) return "The server sent an invalid maze. Please try again.";
  return `Unexpected error: ${e instanceof Error ? e.message : String(e)}`;
}

const timerText = (ms: number): string => fmtMs(ms).slice(0, -1);

function button(label: string, color: string, onclick: () => void, extra = ""): HTMLButtonElement {
  return h("button", { class: `btn ${color} ${extra}`.trim(), type: "button", onclick }, label);
}

function topbar(title: string, onBack: () => void, right?: HTMLElement): HTMLElement {
  return h("header", { class: "topbar" }, button("BACK", "cyan small", onBack), h("h2", {}, title), right ?? h("span", { class: "spacer" }));
}

/** The three colour buttons; `refresh()` shows the active colour and which paths are complete. */
function colourBar(board: () => GameBoard | null) {
  const buttons = new Map<PathColor, HTMLButtonElement>();
  const bar = h("div", { class: "colours" });
  for (const color of PATH_COLORS) {
    const b = button(color.toUpperCase(), color, () => board()?.select(color));
    buttons.set(color, b);
    bar.append(b);
  }
  const refresh = () => {
    const bd = board();
    if (!bd) return;
    const done = bd.manager.completedColors();
    for (const [color, b] of buttons) {
      b.classList.toggle("dim", color !== bd.manager.active);
      b.textContent = color.toUpperCase() + (done.includes(color) ? "  OK" : "");
    }
  };
  return { bar, refresh };
}

// ------------------------------------------------------------------------------ menu
export function menuScreen(ctx: Ctx, root: HTMLElement): Cleanup {
  const who = ctx.account?.signedIn ? `Signed in as ${ctx.account.username ?? "..."}` : "Playing as guest";
  root.append(
    h(
      "main",
      { class: "screen center" },
      h("h1", { class: "logo" }, "MAZE GAME"),
      h("p", { class: "sub" }, "three paths. one exit."),
      h("p", { class: "who" }, who),
      button("PLAY", "blue big", () => ctx.go("levels")),
      button("DAILY CHALLENGE", "green big", () => ctx.go("daily")),
      button("ACCOUNT", "gold", () => ctx.go("account")),
    ),
  );
  return none;
}

// ------------------------------------------------------------------------------ levels
export function levelsScreen(ctx: Ctx, root: HTMLElement): Cleanup {
  const grid = h("div", { class: "levels" });
  for (let n = 1; n <= MAX_LEVEL; n++) {
    const unlocked = ctx.progress.isUnlocked(n);
    const done = ctx.progress.isCompleted(n);
    const best = ctx.progress.bestTime(n);
    const b = h(
      "button",
      { class: `btn level ${done ? "green" : unlocked ? "blue" : "locked"}`, type: "button", disabled: !unlocked, title: best ? `Best ${fmtMs(best)}` : undefined, onclick: () => ctx.go("play", n) },
      String(n),
    );
    grid.append(b);
  }
  root.append(h("main", { class: "screen" }, topbar("LEVELS", () => ctx.go("menu")), grid));
  return none;
}

// ------------------------------------------------------------------------------ classic play
export function playScreen(ctx: Ctx, root: HTMLElement, level: number): Cleanup {
  if (!ctx.progress.isUnlocked(level)) {
    ctx.go("levels");
    return none;
  }
  const maze = buildLevel(level);
  const timer = h("span", { class: "timer" }, "0:00.0");
  const hasKeyboard = typeof matchMedia === "function" && matchMedia("(hover: hover) and (pointer: fine)").matches;
  const status = h("p", { class: "status" }, hasKeyboard ? "Draw from the cyan start to the gold exit  |  keys: 1-3 colour, arrows, R reset" : "Draw from the cyan start to the gold exit");
  const wrap = h("div", { class: "board-wrap" });
  const overlay = h("div", { class: "overlay hidden" });
  let board: GameBoard | null = null;
  const colours = colourBar(() => board);
  const t0 = performance.now();
  let elapsed = 0;
  let finished = false;
  const tick = setInterval(() => {
    if (!finished) {
      elapsed = performance.now() - t0;
      timer.textContent = timerText(elapsed);
    }
  }, 100);

  const win = () => {
    finished = true;
    elapsed = performance.now() - t0;
    timer.textContent = timerText(elapsed);
    if (board) board.disabled = true;
    const info = ctx.progress.recordWin(level, elapsed);
    const panel = h(
      "div",
      { class: "panel" },
      h("h2", { class: "win" }, "LEVEL CLEARED"),
      h("p", {}, `Level ${level}  -  time ${fmtMs(elapsed)}`),
      info.newBest ? h("p", { class: "gold-text" }, "NEW BEST TIME") : null,
      info.unlocked ? h("p", { class: "gold-text" }, `LEVEL ${info.unlocked} UNLOCKED`) : null,
      ctx.progress.isUnlocked(level + 1) && level < MAX_LEVEL ? button("NEXT LEVEL", "green", () => ctx.go("play", level + 1)) : null,
      button("REPLAY", "blue", () => {
        ctx.go("levels");
        setTimeout(() => ctx.go("play", level), 0);
      }),
      button("LEVELS", "cyan", () => ctx.go("levels")),
    );
    overlay.replaceChildren(panel);
    overlay.classList.remove("hidden");
  };

  root.append(
    h("main", { class: "screen" }, topbar(`LEVEL ${level}`, () => ctx.go("levels"), timer), wrap, status, h("div", { class: "controls" }, colours.bar, button("RESET", "gold", () => board?.resetActive()))),
    overlay,
  );
  board = new GameBoard(
    wrap,
    maze,
    {
      onChange: colours.refresh,
      onBlocked: (r) => (status.textContent = r === "blocked_self" ? "A path cannot cross itself." : "Wall! Pull back and try another route."),
      onCompleted: win,
    },
    ctx.glow,
  );
  colours.refresh();
  return () => {
    clearInterval(tick);
    board?.destroy();
  };
}

// ------------------------------------------------------------------------------ daily: leaderboard
export function dailyScreen(ctx: Ctx, root: HTMLElement): Cleanup {
  const message = h("p", { class: "status" });
  const table = h("div", { class: "board-table" });
  const play = button("PLAY TODAY'S MAZE", "green big", () => ctx.go("dailyplay"));
  root.append(
    h(
      "main",
      { class: "screen" },
      topbar("DAILY CHALLENGE", () => ctx.go("menu")),
      h("p", { class: "sub" }, `${new Date().toISOString().slice(0, 10)} (UTC)  -  same maze for every player`),
      play,
      message,
      table,
      h("div", { class: "controls" }, button("REFRESH", "blue", () => void load()), button("ACCOUNT", "gold", () => ctx.go("account"))),
    ),
  );
  let alive = true;
  async function load() {
    if (!ctx.daily) return;
    try {
      const rows = await ctx.daily.leaderboard();
      if (!alive) return;
      table.replaceChildren();
      if (!rows.length) table.append(h("p", { class: "sub" }, "No times yet today - be the first!"));
      for (const r of rows) {
        table.append(h("div", { class: `row ${r.isMe ? "me" : ""}` }, h("span", {}, `#${r.rank}`), h("span", {}, r.username), h("span", {}, fmtMs(r.elapsedMs))));
      }
    } catch (e) {
      if (alive) message.textContent = errorText(e);
    }
  }
  if (!ctx.account || !ctx.daily) {
    message.textContent = "Online features are not configured in this build.";
    play.disabled = true;
  } else {
    const ready = ctx.account.signedIn && !!ctx.account.username;
    play.disabled = !ready;
    message.textContent = ready ? "" : "Sign in (and pick a username) to play and appear on the board.";
    void load();
  }
  return () => {
    alive = false;
  };
}

// ------------------------------------------------------------------------------ daily: play
export function dailyPlayScreen(ctx: Ctx, root: HTMLElement): Cleanup {
  const daily = ctx.daily;
  const timer = h("span", { class: "timer" }, "0:00.0");
  const status = h("p", { class: "status" }, "Starting...");
  const wrap = h("div", { class: "board-wrap" });
  const actions = h("div", { class: "controls" });
  let board: GameBoard | null = null;
  let run: DailyRun | null = null;
  let t0 = 0;
  let finished = true;
  let alive = true;
  const colours = colourBar(() => board);
  const tick = setInterval(() => {
    if (!finished) timer.textContent = timerText(performance.now() - t0);
  }, 100);

  const showEnd = () => actions.replaceChildren(button("PLAY AGAIN", "green", () => void begin()), button("LEADERBOARD", "blue", () => ctx.go("daily")));

  async function submit() {
    if (!daily || !run) return;
    finished = true;
    if (board) board.disabled = true;
    status.textContent = "Submitting to the server...";
    try {
      const res = await daily.submit(run, board!.manager.path("blue").cells);
      if (!alive) return;
      status.textContent = res.accepted ? `RANK #${res.rank}   your time ${fmtMs(res.elapsedMs)}   (best ${fmtMs(res.bestMs ?? res.elapsedMs)})` : `Run rejected: ${res.message}`;
    } catch (e) {
      if (alive) status.textContent = `Could not submit: ${errorText(e)}`;
    }
    if (alive) showEnd();
  }

  async function begin() {
    if (!daily) return;
    board?.destroy();
    board = null;
    actions.replaceChildren();
    status.textContent = "Starting...";
    try {
      run = await daily.start();
    } catch (e) {
      if (!alive) return;
      status.textContent = errorText(e);
      showEnd();
      return;
    }
    if (!alive) return;
    board = new GameBoard(wrap, run.maze, { onChange: colours.refresh, onCompleted: () => void submit() }, ctx.glow);
    board.select("blue");
    t0 = performance.now();
    finished = false;
    status.textContent = "Draw the BLUE path from start to exit. The clock is already running!";
    actions.replaceChildren(button("RESET", "gold", () => board?.resetActive()));
  }

  root.append(h("main", { class: "screen" }, topbar("DAILY", () => ctx.go("daily"), timer), wrap, status, actions));
  if (!daily || !ctx.account?.signedIn) {
    status.textContent = "Sign in to play the daily challenge.";
    actions.append(button("ACCOUNT", "gold", () => ctx.go("account")));
  } else {
    void begin();
  }
  return () => {
    alive = false;
    clearInterval(tick);
    board?.destroy();
  };
}

// ------------------------------------------------------------------------------ account
export function accountScreen(ctx: Ctx, root: HTMLElement): Cleanup {
  const account: Account | null = ctx.account;
  const state = h("p", { class: "who" });
  const message = h("p", { class: "status" });
  const email = h("input", { type: "email", placeholder: "e-mail", autocomplete: "email", class: "field" });
  const password = h("input", { type: "password", placeholder: "password (6+ characters)", autocomplete: "current-password", class: "field" });
  const username = h("input", { type: "text", placeholder: "username (3-20 letters, digits, _)", autocomplete: "username", maxlength: "20", class: "field" });
  let busy = false;
  const btnIn = button("SIGN IN", "blue", () => void run(() => signIn()));
  const btnUp = button("CREATE ACCOUNT", "green", () => void run(() => signUp()));
  const btnName = button("SET USERNAME", "gold", () => void run(() => setName()));
  const btnOut = button("SIGN OUT", "red", () => {
    account?.signOut();
    message.textContent = "Signed out. Your progress stays on this device.";
    refresh();
  });

  function refresh() {
    if (!account) {
      state.textContent = "Online features are not configured in this build. You can keep playing as a guest.";
      for (const el of [email, password, username, btnIn, btnUp, btnName, btnOut]) el.disabled = true;
      return;
    }
    const signed = account.signedIn;
    const needsName = signed && !account.username;
    state.textContent = signed && account.username ? `Signed in as ${account.username}` : needsName ? "Signed in - choose a username" : "Playing as guest";
    email.disabled = password.disabled = signed || busy;
    username.disabled = (signed && !needsName) || busy;
    btnIn.disabled = btnUp.disabled = signed || busy;
    btnName.disabled = !needsName || busy;
    btnOut.disabled = !signed || busy;
  }

  function validate(needUsername: boolean): string | null {
    if (!/^\S+@\S+\.\S+$/.test(email.value.trim())) return "Enter a valid e-mail.";
    if (password.value.length < 6) return "Password must have at least 6 characters.";
    if (needUsername && !USERNAME_RE.test(username.value.trim())) return "Username must be 3-20 letters, digits or underscore.";
    return null;
  }

  async function run(fn: () => Promise<void>) {
    busy = true;
    refresh();
    try {
      await fn();
    } catch (e) {
      message.textContent = errorText(e);
    }
    busy = false;
    password.value = "";
    refresh();
  }

  async function signIn() {
    const problem = validate(false);
    if (problem) return void (message.textContent = problem);
    message.textContent = "Signing in...";
    const s = await account!.signIn(email.value.trim(), password.value);
    message.textContent = s === "needs_username" ? "Signed in. Choose a username to join the leaderboards." : "Welcome!";
  }

  async function signUp() {
    const problem = validate(true);
    if (problem) return void (message.textContent = problem);
    message.textContent = "Creating account...";
    const s = await account!.signUp(email.value.trim(), password.value, username.value.trim());
    message.textContent = s === "confirm_email" ? "Account created! Confirm your e-mail, then sign in." : "Welcome!";
  }

  async function setName() {
    if (!USERNAME_RE.test(username.value.trim())) return void (message.textContent = "Username must be 3-20 letters, digits or underscore.");
    await account!.setUsername(username.value.trim());
    message.textContent = "Username saved.";
  }

  root.append(h("main", { class: "screen center" }, topbar("ACCOUNT", () => ctx.go("menu")), state, email, password, username, btnIn, btnUp, btnName, btnOut, message));
  refresh();
  if (account?.signedIn && !account.username) {
    void account.refreshProfile().then(refresh, () => {});
  }
  return none;
}
