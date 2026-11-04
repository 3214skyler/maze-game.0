"""Sign in / create account / sign out. Guest play stays available: the game never requires an account."""
import re

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.textinput import TextInput

from game.online.account import AccountStatus
from game.online.errors import AuthError, NetworkError, OnlineError, ServerError
from interface.components import async_task
from interface.screens.menu import neon_button
from interface.themes import neon

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


def describe(exc: Exception) -> str:
    if isinstance(exc, NetworkError):
        return "No connection. Check your internet and try again."
    if isinstance(exc, (AuthError, ServerError)):
        return str(exc)
    return f"Unexpected error: {exc}"


def _field(hint, **kw):
    return TextInput(hint_text=hint, multiline=False, size_hint_y=None, height=44, write_tab=False,
                     background_color=neon.PANEL, foreground_color=(1, 1, 1, 1),
                     hint_text_color=(0.5, 0.55, 0.7, 1), cursor_color=neon.ACCENT,
                     disabled_foreground_color=(0.7, 0.75, 0.9, 1), **kw)


class AccountScreen(Screen):
    def __init__(self, account, repo, service, **kwargs):
        super().__init__(name="account", **kwargs)
        self.account, self.repo, self.service = account, repo, service
        box = BoxLayout(orientation="vertical", padding=24, spacing=8)
        box.add_widget(Label(text="ACCOUNT", font_size="28sp", bold=True, color=neon.ACCENT,
                             size_hint_y=None, height=56))
        self.state = Label(color=neon.GOLD, size_hint_y=None, height=44, halign="center")
        self.state.bind(size=lambda w, s: setattr(w, "text_size", s))
        box.add_widget(self.state)
        self.email = _field("e-mail", input_type="mail")
        self.password = _field("password (6+ characters)", password=True)
        self.username = _field("username (3-20 letters, digits, _)")
        for w in (self.email, self.password, self.username):
            box.add_widget(w)
        self.in_btn = neon_button("SIGN IN", neon.PATH_RGBA["blue"], size_hint_y=None, height=50)
        self.up_btn = neon_button("CREATE ACCOUNT", neon.PATH_RGBA["green"], size_hint_y=None, height=50)
        self.name_btn = neon_button("SET USERNAME", neon.GOLD, size_hint_y=None, height=50)
        self.out_btn = neon_button("SIGN OUT", neon.PATH_RGBA["red"], size_hint_y=None, height=50)
        self.in_btn.bind(on_release=lambda *_: self.do_sign_in())
        self.up_btn.bind(on_release=lambda *_: self.do_sign_up())
        self.name_btn.bind(on_release=lambda *_: self.do_set_username())
        self.out_btn.bind(on_release=lambda *_: self.do_sign_out())
        for b in (self.in_btn, self.up_btn, self.name_btn, self.out_btn):
            box.add_widget(b)
        self.message = Label(color=(0.8, 0.85, 1, 1), size_hint_y=1, halign="center", valign="top")
        self.message.bind(size=lambda w, s: setattr(w, "text_size", s))
        box.add_widget(self.message)
        back = neon_button("BACK", neon.ACCENT, size_hint_y=None, height=48)
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "menu"))
        box.add_widget(back)
        self.add_widget(box)
        self.busy = False
        self.refresh()

    # --- view state ---------------------------------------------------------------------
    def refresh(self):
        acc = self.account
        if acc is None:
            self.state.text = "Online features are not configured in this build.\nYou can keep playing as a guest."
            for w in (self.email, self.password, self.username, self.in_btn, self.up_btn, self.name_btn, self.out_btn):
                w.disabled = True
            return
        signed = acc.signed_in
        needs_name = signed and not acc.username
        cloud = {"synced": "cloud save: up to date", "offline": "cloud save: offline (will retry)",
                 "local": "", "cloud_newer": "cloud save: newer progress found, reopen to load it"
                 }.get(self.repo.status, f"cloud save: {self.repo.status}")
        self.state.text = (f"Signed in as {acc.username}\n{cloud}" if signed and acc.username else
                           "Signed in - choose a username" if needs_name else "Playing as guest")
        for w in (self.email, self.password):
            w.disabled = signed
        self.username.disabled = signed and not needs_name
        self.in_btn.disabled = self.up_btn.disabled = signed or self.busy
        self.name_btn.disabled = not needs_name or self.busy
        self.out_btn.disabled = not signed or self.busy

    def on_enter(self, *_):
        self.refresh()

    def _say(self, text):
        self.message.text = text

    # --- actions -------------------------------------------------------------------------------
    def _validate(self, need_username):
        email, pw, name = self.email.text.strip(), self.password.text, self.username.text.strip()
        if "@" not in email or "." not in email:
            return "Enter a valid e-mail."
        if len(pw) < 6:
            return "Password must have at least 6 characters."
        if need_username and not USERNAME_RE.match(name):
            return "Username must be 3-20 letters, digits or underscore."
        return None

    def _run(self, work, done, busy_text):
        self.busy = True
        self._say(busy_text)
        self.refresh()

        def ok(result):
            self.busy = False
            done(result)
            self.refresh()

        def fail(exc):
            self.busy = False
            self._say(describe(exc))
            self.refresh()

        async_task.run_async(work, ok, fail)

    def do_sign_in(self):
        problem = self._validate(False)
        if problem:
            return self._say(problem)
        email, pw = self.email.text.strip(), self.password.text
        self._run(lambda: self.account.sign_in(email, pw), self._after_login, "Signing in...")

    def do_sign_up(self):
        problem = self._validate(True)
        if problem:
            return self._say(problem)
        email, pw, name = self.email.text.strip(), self.password.text, self.username.text.strip()
        self._run(lambda: self.account.sign_up(email, pw, name), self._after_login, "Creating account...")

    def do_set_username(self):
        name = self.username.text.strip()
        if not USERNAME_RE.match(name):
            return self._say("Username must be 3-20 letters, digits or underscore.")
        self._run(lambda: self.account.set_username(name), lambda _r: self._after_login(AccountStatus.SIGNED_IN),
                  "Saving username...")

    def _after_login(self, status):
        self.password.text = ""
        if status is AccountStatus.CONFIRM_EMAIL:
            return self._say("Account created! Confirm your e-mail, then sign in.")
        if status is AccountStatus.NEEDS_USERNAME:
            self._say("Signed in. Choose a username to join the leaderboards.")
        else:
            self._say("Welcome!")
        self.repo.attach(self.account.api)
        # reading the cloud save may hit the network: do it off the UI thread, apply on the UI thread
        async_task.run_async(self.repo.load, lambda data: (self.service.reload(data), self.refresh()),
                             lambda exc: self._say(describe(exc)))

    def do_sign_out(self):
        self.repo.detach()
        self.account.sign_out()
        self._say("Signed out. Your progress stays on this device.")
        self.refresh()
