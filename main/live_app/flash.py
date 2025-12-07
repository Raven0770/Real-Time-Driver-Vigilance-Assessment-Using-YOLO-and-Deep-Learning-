# live_app/flash.py
import time
import tkinter as tk
from datetime import datetime, time as dt_time
import cv2
import config

# small helper: hex <-> rgb
def hex_to_rgb(hx: str):
    hx = hx.lstrip("#")
    return tuple(int(hx[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, int(rgb[0]))),
        max(0, min(255, int(rgb[1]))),
        max(0, min(255, int(rgb[2])))
    )

def mix_color(rgb, intensity):
    """Scale rgb by intensity (0..1) around black (simple brightness)."""
    return (rgb[0] * intensity, rgb[1] * intensity, rgb[2] * intensity)

class FlashController:
    """
    Controls flash overlay on top of the video panel.

    API:
      - set_color(hexcolor)            : set single color used by _flash_once/demo
      - demo_flash(duration=0.6)       : flash once (short)
      - start_loop(last_frame_getter)  : older simple loop (kept for compatibility)
      - start_color_cycle(colors, ramp_seconds, gap_seconds)
      - stop_loop()
    """

    def __init__(self, video_panel, video_label, parent_after):
        """
        video_panel: widget to place overlay into
        video_label: the CTkLabel showing video (used for stacking)
        parent_after: function reference to call .after(ms, func) (usually parent.after)
        """
        self.video_panel = video_panel
        self.video_label = video_label
        self.after = parent_after
        self.flash_color = "#FFFFFF"
        self._flash_overlay = None
        self._flash_running = False
        self._flash_job = None
        self._flash_next = 0.0

        # color-cycle state
        self._cycle_running = False
        self._cycle_job = None
        self._cycle_colors = []
        self._cycle_index = 0
        self._cycle_phase = None
        self._cycle_phase_start = 0.0
        self._cycle_ramp = 5.0
        self._cycle_gap = 10.0
        self._cycle_min_intensity = 0.20
        self._tick_ms = int(getattr(config, "FLASH_TICK_MS", 80))

    # ---------- compatibility/simple methods ----------
    def set_color(self, hexcolor):
        """Set the single color used by demo/_flash_once"""
        self.flash_color = hexcolor

    def demo_flash(self, duration=0.6):
        """One quick flash (keeps previous behavior)"""
        self._flash_once(duration=duration, color=self.flash_color)

    def _is_dark_condition(self, last_frame):
        """
        Heuristic: dark if time is night or frame mean below threshold.
        last_frame: BGR numpy array or None
        """
        try:
            now = datetime.now().time()
            # night time by config boundaries (best-effort)
            start = getattr(config, "FLASH_NIGHT_START", 18)
            end = getattr(config, "FLASH_NIGHT_END", 6)
            end_min = getattr(config, "FLASH_NIGHT_END_MIN", 30)
            h = now.hour; m = now.minute
            if (h >= start) or (h < end) or (h == end and m < end_min):
                return True
        except Exception:
            pass
        try:
            if last_frame is None:
                return False
            g = cv2.cvtColor(last_frame, cv2.COLOR_BGR2GRAY)
            return float(g.mean()) < 60.0
        except Exception:
            return False

    def start_loop(self, last_frame_getter):
        """
        Legacy: every X seconds, if it's dark, flash once for short duration.
        Kept for backward compatibility with older code.
        """
        if self._flash_running:
            return
        self._flash_running = True
        self._flash_next = time.time() + 3.0

        def _loop():
            if not self._flash_running:
                return
            now_ts = time.time()
            try:
                dark = self._is_dark_condition(last_frame_getter())
                if dark and now_ts >= self._flash_next:
                    hour = datetime.now().hour
                    duration = 1.0 if (hour >= 18 or hour < 6 or (hour == 6 and datetime.now().minute < 30)) else 0.5
                    self._flash_once(duration=duration, color=self.flash_color)
                    self._flash_next = now_ts + getattr(config, "FLASH_INTERVAL_S", 30.0)
            except Exception:
                pass
            self._flash_job = self.after(1000, _loop)
        _loop()

    # ---------- stop / cleanup ----------
    def stop_loop(self):
        """Stop both legacy loop and color cycle."""
        self._flash_running = False
        if self._flash_job:
            try:
                self.after_cancel(self._flash_job)
            except Exception:
                pass
            self._flash_job = None

        self._stop_color_cycle()

        # remove overlay if present
        if self._flash_overlay:
            try:
                self._flash_overlay.place_forget()
                self._flash_overlay.destroy()
            except Exception:
                pass
            self._flash_overlay = None

    # ---------- single flash helper (kept) ----------
    def _flash_once(self, duration=0.5, color="#FFFFFF"):
        # create overlay frame if needed
        try:
            if self._flash_overlay is None:
                ov = tk.Frame(self.video_panel, bg=color)
                ov.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
                try:
                    ov.lift(aboveThis=self.video_label)
                except Exception:
                    pass
                self._flash_overlay = ov
            else:
                try:
                    self._flash_overlay.configure(bg=color)
                    self._flash_overlay.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
                    self._flash_overlay.lift(aboveThis=self.video_label)
                except Exception:
                    pass
        except Exception:
            return

        def _remove():
            try:
                if self._flash_overlay:
                    self._flash_overlay.place_forget()
            except Exception:
                pass

        try:
            self.after(int(duration * 1000), _remove)
        except Exception:
            _remove()

    # ---------- new: color cycle (ramp up -> ramp down -> gap -> switch color) ----------
    def start_color_cycle(self, colors=None, ramp_seconds=None, gap_seconds=None, min_intensity=0.20):
        """
        Start the alternating ramp animation.
        colors: list of hex strings (e.g. ["#ff3333", "#ffd100"])
        ramp_seconds: seconds to ramp up (and ramp down)
        gap_seconds: seconds to wait between color switches
        min_intensity: lowest intensity factor (0..1)
        """
        if not colors or len(colors) < 2:
            # fall back to configured defaults
            c1 = getattr(config, "FLASH_COLOR_1", "#ff3333")
            c2 = getattr(config, "FLASH_COLOR_2", "#ffd100")
            colors = [c1, c2]

        self._cycle_colors = list(colors)
        self._cycle_index = 0
        self._cycle_ramp = float(ramp_seconds) if ramp_seconds is not None else float(getattr(config, "FLASH_RAMP_SECONDS", 5.0))
        self._cycle_gap = float(gap_seconds) if gap_seconds is not None else float(getattr(config, "FLASH_GAP_SECONDS", 10.0))
        self._cycle_min_intensity = float(min_intensity)
        self._tick_ms = int(getattr(config, "FLASH_TICK_MS", 80))
        if self._cycle_ramp <= 0:
            self._cycle_ramp = 5.0
        if self._cycle_gap < 0:
            self._cycle_gap = 10.0

        # stop existing cycle if any
        self._stop_color_cycle()
        self._cycle_running = True
        # initialize phase
        self._cycle_phase = "ramp_up"
        self._cycle_phase_start = time.time()
        # create overlay if necessary
        if self._flash_overlay is None:
            try:
                ov = tk.Frame(self.video_panel, bg=self._cycle_colors[self._cycle_index])
                ov.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
                try:
                    ov.lift(aboveThis=self.video_label)
                except Exception:
                    pass
                self._flash_overlay = ov
            except Exception:
                self._flash_overlay = None

        # schedule first tick immediately
        self._cycle_step()

    def _stop_color_cycle(self):
        self._cycle_running = False
        if self._cycle_job:
            try:
                self.after_cancel(self._cycle_job)
            except Exception:
                pass
            self._cycle_job = None

    def _cycle_step(self):
        """Single tick for the color cycle animation."""
        if not self._cycle_running:
            return

        now = time.time()
        phase = self._cycle_phase or "ramp_up"
        elapsed = now - self._cycle_phase_start
        ramp = float(self._cycle_ramp)
        gap = float(self._cycle_gap)

        try:
            # ensure overlay present
            if self._flash_overlay is None:
                ov = tk.Frame(self.video_panel, bg=self._cycle_colors[self._cycle_index])
                ov.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
                try: ov.lift(aboveThis=self.video_label)
                except Exception: pass
                self._flash_overlay = ov
        except Exception:
            pass

        # compute intensity based on phase
        intensity = 0.0
        next_phase = phase
        if phase == "ramp_up":
            if elapsed >= ramp:
                intensity = 1.0
                next_phase = "ramp_down"
            else:
                # linear ramp from min -> 1.0
                ratio = max(0.0, min(1.0, elapsed / ramp))
                intensity = self._cycle_min_intensity + ratio * (1.0 - self._cycle_min_intensity)
        elif phase == "ramp_down":
            if elapsed >= ramp:
                intensity = self._cycle_min_intensity
                next_phase = "gap"
            else:
                # linear ramp from 1.0 -> min
                ratio = max(0.0, min(1.0, elapsed / ramp))
                intensity = 1.0 - ratio * (1.0 - self._cycle_min_intensity)
        elif phase == "gap":
            intensity = 0.0
            if elapsed >= gap:
                # switch to next color and restart ramp_up
                self._cycle_index = (self._cycle_index + 1) % len(self._cycle_colors)
                next_phase = "ramp_up"
                self._cycle_phase_start = now
        else:
            # unknown phase -> reset
            next_phase = "ramp_up"
            self._cycle_phase_start = now
            intensity = self._cycle_min_intensity

        # update overlay color using current color * intensity
        try:
            base_hex = self._cycle_colors[self._cycle_index]
            rgb = hex_to_rgb(base_hex)
            scaled = mix_color(rgb, intensity)
            hex_now = rgb_to_hex(scaled)
            if self._flash_overlay:
                try:
                    self._flash_overlay.configure(bg=hex_now)
                    # ensure overlay visible while intensity > 0
                    if intensity > 0.001:
                        self._flash_overlay.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
                        try:
                            self._flash_overlay.lift(aboveThis=self.video_label)
                        except Exception:
                            pass
                    else:
                        # hide overlay when intensity is effectively zero
                        try:
                            self._flash_overlay.place_forget()
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

        # advance phase/time if we switched phase earlier
        if next_phase != phase:
            # set next phase and its start time
            self._cycle_phase = next_phase
            self._cycle_phase_start = now
        # schedule next tick
        try:
            self._cycle_job = self.after(self._tick_ms, self._cycle_step)
        except Exception:
            # as a fallback, use time.sleep (should not happen)
            time.sleep(self._tick_ms / 1000.0)
            self._cycle_step()
