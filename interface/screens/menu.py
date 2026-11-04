from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from interface.themes import neon


def neon_button(text, rgba, **kwargs):
    btn = Button(text=text, background_normal="", background_disabled_normal="", background_color=rgba,
                 color=(0.03, 0.04, 0.07, 1), disabled_color=(0.03, 0.04, 0.07, 1), bold=True, **kwargs)
    btn.bind(disabled=lambda w, off: setattr(w, "opacity", 0.4 if off else 1.0))   # disabled must look disabled
    return btn


class MenuScreen(Screen):
    def __init__(self, service=None, account=None, **kwargs):
        super().__init__(name="menu", **kwargs)
        self.service = service
        self.account = account
        box = BoxLayout(orientation="vertical", padding=40, spacing=16)
        box.add_widget(Label(text="MAZE GAME", font_size="40sp", bold=True, color=neon.ACCENT, size_hint_y=2))
        self.summary = Label(color=neon.GOLD, font_size="14sp", size_hint_y=None, height=30)
        box.add_widget(self.summary)
        play = neon_button("PLAY", neon.PATH_RGBA["blue"], size_hint_y=None, height=64)
        play.bind(on_release=lambda *_: setattr(self.manager, "current", "levels"))
        daily = neon_button("DAILY CHALLENGE", neon.PATH_RGBA["green"], size_hint_y=None, height=56)
        daily.bind(on_release=lambda *_: setattr(self.manager, "current", "daily"))
        acct = neon_button("ACCOUNT", neon.GOLD, size_hint_y=None, height=48)
        acct.bind(on_release=lambda *_: setattr(self.manager, "current", "account"))
        quit_ = neon_button("QUIT", neon.PATH_RGBA["red"], size_hint_y=None, height=56)
        quit_.bind(on_release=lambda *_: App.get_running_app().stop())
        box.add_widget(play)
        box.add_widget(daily)
        box.add_widget(acct)
        box.add_widget(quit_)
        self.warning = Label(color=neon.PATH_RGBA["red"], font_size="11sp", size_hint_y=None, height=40)
        box.add_widget(self.warning)
        box.add_widget(Label(size_hint_y=1))
        self.add_widget(box)

    def on_enter(self, *_):
        svc = self.service
        if svc is None:
            return
        who = "guest" if not (self.account and self.account.signed_in) else (self.account.username or "signed in")
        self.summary.text = (f"{who}   PLAYER LV {svc.player_level()}   $ {svc.coins}   "
                             f"LIVES {svc.lives()}/{svc.cfg.max_lives}")
        notes = [m for m in (svc.load_warning, svc.save_error and "Progress could not be saved: " + svc.save_error) if m]
        self.warning.text = "\n".join(notes)
