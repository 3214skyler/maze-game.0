"""Run slow work (network) off the UI thread and deliver the result back on it."""
import threading

from kivy.clock import Clock

RUN_SYNC = False        # tests set this to True to run inline and deterministically


def run_async(fn, on_done, on_error=None):
    if RUN_SYNC:
        try:
            result = fn()
        except Exception as exc:               # noqa: BLE001 - UI must show any failure, never crash
            if on_error:
                on_error(exc)
            return
        on_done(result)
        return

    def worker():
        try:
            result = fn()
        except Exception as exc:               # noqa: BLE001
            if on_error:
                Clock.schedule_once(lambda _dt, e=exc: on_error(e))
            return
        Clock.schedule_once(lambda _dt, r=result: on_done(r))

    threading.Thread(target=worker, daemon=True).start()
