# live_app/break_timer.py
import time
from datetime import datetime, time as dt_time
import tkinter as tk

class BreakTimer:
    def __init__(self, parent_after, callback_on_update, show_modal_fn=None):
        """
        parent_after: parent's .after function
        callback_on_update: function(dict) -> receives {"elapsed_s","next_prompt_s","is_night"}
        show_modal_fn: callable(parent, brief)-> returns user action (or None) — used to show BreakReminderDialog from UI
        """
        self.after = parent_after
        self.callback_on_update = callback_on_update
        self.show_modal_fn = show_modal_fn
        self._running = False
        self._job = None
        self._start = None
        self._snooze_until = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._start = time.time()
        self._snooze_until = None
        self._job = self.after(10 * 1000, self._check)

    def stop(self):
        self._running = False
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self._start = None
        self._snooze_until = None

    def snooze(self, minutes):
        self._snooze_until = time.time() + (minutes * 60)

    def _check(self):
        if not self._running:
            return
        now = time.time()
        if self._snooze_until and now < self._snooze_until:
            self._job = self.after(10 * 1000, self._check)
            return
        elapsed = now - (self._start or now)
        tnow = datetime.now().time()
        is_night = (tnow >= dt_time(18, 0)) or (tnow < dt_time(6, 30))

        # compute next prompt heuristic
        next_prompt = None
        if is_night:
            if 3600 < elapsed < 2 * 3600:
                next_prompt = int(2 * 3600 - elapsed)
            elif elapsed >= 2 * 3600:
                next_prompt = 0
            else:
                next_prompt = int(3600 - elapsed)
        else:
            if elapsed >= 3 * 3600:
                next_prompt = 0
            else:
                next_prompt = int(3 * 3600 - elapsed)

        # callback update
        try:
            if self.callback_on_update:
                self.callback_on_update({"elapsed_s": int(elapsed), "next_prompt_s": next_prompt, "is_night": bool(is_night)})
        except Exception:
            pass

        # show modal if needed
        try:
            if self.show_modal_fn:
                if is_night and 3600 < elapsed < 2 * 3600:
                    self.show_modal_fn(brief=True)
                elif is_night and elapsed >= 2 * 3600:
                    self.show_modal_fn(brief=False)
                elif not is_night and elapsed >= 3 * 3600:
                    self.show_modal_fn(brief=False)
        except Exception:
            pass

        # schedule next
        self._job = self.after(10 * 1000, self._check)
