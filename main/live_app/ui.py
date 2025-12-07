# live_app/ui.py
import os
import time
import cv2
import customtkinter as ctk
import tkinter as tk
from PIL import Image
from datetime import datetime
from collections import deque

from .detector import Detector, get_ip_location
from .flash import FlashController
from .break_timer import BreakTimer
from . import logger as logmod
import config

# Small CTk messagebox used inside (kept simple)
class CTkMessagebox(ctk.CTkToplevel):
    def __init__(self, parent, title="Message", message=""):
        super().__init__(parent)
        self.title(title)
        self.geometry("420x160")
        self.resizable(False, False)
        lbl = ctk.CTkLabel(self, text=message, wraplength=380, justify="left")
        lbl.pack(padx=12, pady=12)
        btn = ctk.CTkButton(self, text="OK", command=self.destroy)
        btn.pack(pady=(0,12))
        try:
            self.grab_set(); self.transient(parent)
        except Exception:
            pass

# Break dialog used by BreakTimer (UI-level)
class BreakReminderDialog(ctk.CTkToplevel):
    def __init__(self, parent, title="Break Reminder", message="Time for a break"):
        super().__init__(parent)
        self.title(title); self.geometry("480x180"); self.resizable(False, False)
        self.result = None
        ctk.CTkLabel(self, text=message, wraplength=440, font=ctk.CTkFont(size=12)).pack(padx=12, pady=(12,8))
        btn_frame = ctk.CTkFrame(self); btn_frame.pack(pady=(8,12))
        ctk.CTkButton(btn_frame, text="Take Break", width=120, command=self._take_break).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Snooze 15m", width=120, command=self._snooze).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Dismiss", width=120, command=self._dismiss).pack(side="left", padx=6)
        try:
            self.transient(parent); self.grab_set(); self.focus_force()
        except Exception:
            pass

    def _take_break(self): self.result = "break"; self.destroy()
    def _snooze(self): self.result = "snooze"; self.destroy()
    def _dismiss(self): self.result = "dismiss"; self.destroy()

class DrowsinessFrame(ctk.CTkFrame):
    def __init__(self, parent,
                 model_dir=config.MODEL_DIR,
                 log_dir=config.LOG_DIR,
                 report_dir=config.REPORT_DIR,
                 sound_dir=config.SOUND_DIR,
                 video_width=640, video_height=480,
                 on_alertness=None, on_break_update=None, on_dashboard=None):
        super().__init__(parent)
        self.parent = parent
        self.model_dir = model_dir
        self.log_dir = log_dir
        self.report_dir = report_dir
        self.sound_dir = sound_dir

        # callbacks for launcher
        self.on_alertness = on_alertness
        self.on_break_update = on_break_update
        self.on_dashboard = on_dashboard

        # video / UI state
        self.start_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.start_time = time.time()
        self.base_video_width = video_width
        self.base_video_height = video_height
        self.video_width = video_width
        self.video_height = video_height
        self._last_frame_for_brightness = None

        # detection flags
        self.detection_enabled = False
        self.paused = False

        # rolling alertness samples
        self.ALERT_WINDOW_S = 30
        self._alert_samples = deque()
        self._alert_times = deque()

        # instantiate Detector
        self.detector = Detector(model_dir=self.model_dir, sound_dir=self.sound_dir)

        # UI placeholders
        self.video_label = None
        self.btn_start = None
        self.btn_pause = None
        self.btn_stop = None
        self.status_label = None
        self.yawn_label = None
        self.drowsy_timer_label = None
        self.drowsy_time_slider = None
        self.conf_slider = None
        self.video_size_slider = None
        self.drowsy_val_lbl = None
        self.conf_val_lbl = None
        self.zoom_val_lbl = None
        self.alertness_bar = None
        self.alertness_val_lbl = None

        # log
        self.log_file = None
        self.log_header = ["Timestamp", "EventType", "Details"]

        # controllers (created after UI that provides video_panel)
        self.flash = None
        self.break_timer = None

        # per-second state sampling timestamp (seconds since epoch)
        self._last_state_sample_ts = 0.0

        self._build_ui()

    def _build_ui(self):
        # header
        top = ctk.CTkFrame(self); top.pack(side="top", fill="x", padx=8, pady=8)
        ctk.CTkLabel(top, text="Live Drowsiness Detector", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        btn_frame = ctk.CTkFrame(top); btn_frame.pack(side="right")
        self.btn_start = ctk.CTkButton(btn_frame, text="Start", command=self.start_detection); self.btn_start.pack(side="left", padx=6)
        self.btn_pause = ctk.CTkButton(btn_frame, text="Pause", command=self.pause_detection, state="disabled"); self.btn_pause.pack(side="left", padx=6)
        self.btn_stop = ctk.CTkButton(btn_frame, text="Stop & Report", command=self.on_stop, state="disabled"); self.btn_stop.pack(side="left", padx=6)

        # video panel
        self.video_panel = ctk.CTkFrame(self, fg_color="black"); self.video_panel.pack(fill="both", expand=True, padx=8, pady=8)
        self.video_label = ctk.CTkLabel(self.video_panel, text=""); self.video_label.pack(expand=True, fill="both")

        # --- Right side control panel ---
        self.right_panel = ctk.CTkFrame(self, width=320)
        self.right_panel.pack(side='right', fill='y', padx=8, pady=8)

        # Flash toggle
        self.btn_flash_toggle_rhs = ctk.CTkButton(self.right_panel, text='Toggle Flash (18:00-06:00)', command=self.toggle_flash)
        self.btn_flash_toggle_rhs.pack(pady=6, padx=6)

        # Reset Yawn Counter
        self.btn_reset_yawn_rhs = ctk.CTkButton(self.right_panel, text='Reset Yawn Counter', command=self.reset_yawn_counter_ui)
        self.btn_reset_yawn_rhs.pack(pady=6, padx=6)

        # Drowsy threshold input
        ctk.CTkLabel(self.right_panel, text='Drowsy threshold (s)').pack(pady=(12,2))
        self.entry_drowsy_threshold = ctk.CTkEntry(self.right_panel, placeholder_text='6')
        self.entry_drowsy_threshold.pack(pady=4, padx=6)
        self.btn_apply_threshold = ctk.CTkButton(self.right_panel, text='Apply Threshold', command=self.apply_drowsy_threshold)
        self.btn_apply_threshold.pack(pady=6, padx=6)

        # Test Location button
        self.btn_test_location = ctk.CTkButton(self.right_panel, text='Test Location', command=self.test_location_ui)
        self.btn_test_location.pack(pady=6, padx=6)

        # Track keeper / extra controls
        ctk.CTkLabel(self.right_panel, text='Controls & Track Keeper').pack(pady=(12,4))
        self.chk_track_keeper_var = tk.IntVar(value=1)
        self.chk_track_keeper = ctk.CTkCheckBox(self.right_panel, text='Enable Track Keeper', variable=self.chk_track_keeper_var, onvalue=1, offvalue=0, command=lambda: None)
        self.chk_track_keeper.pack(pady=4)

        # Confidence control (float entry)
        ctk.CTkLabel(self.right_panel, text='Detection Confidence (0-1)').pack(pady=(8,2))
        self.entry_confidence = ctk.CTkEntry(self.right_panel, placeholder_text='0.4')
        self.entry_confidence.pack(pady=4, padx=6)
        self.btn_apply_conf = ctk.CTkButton(self.right_panel, text='Apply Confidence', command=self.apply_confidence)
        self.btn_apply_conf.pack(pady=6, padx=6)


        # status area
        status = ctk.CTkFrame(self); status.pack(fill="x", padx=8, pady=(0,8))
        self.status_label = ctk.CTkLabel(status, text="STATUS: STANDBY"); self.status_label.pack(anchor="w")
        self.yawn_label = ctk.CTkLabel(status, text="Yawn Count: 0"); self.yawn_label.pack(anchor="w")
        self.drowsy_timer_label = ctk.CTkLabel(status, text="Drowsy Timer: 0s"); self.drowsy_timer_label.pack(anchor="w")

        # alertness bar
        mrow = ctk.CTkFrame(status); mrow.pack(fill="x", pady=(6,2))
        ctk.CTkLabel(mrow, text="Alertness").pack(side="left", padx=(4,6))
        self.alertness_val_lbl = ctk.CTkLabel(mrow, text="100%", width=60); self.alertness_val_lbl.pack(side="right", padx=(6,4))
        self.alertness_bar = ctk.CTkProgressBar(status); self.alertness_bar.set(1.0); self.alertness_bar.pack(fill="x", pady=(0,6))

        # sliders with live labels
        drow = ctk.CTkFrame(status); drow.pack(fill="x", pady=(6,2))
        ctk.CTkLabel(drow, text="Drowsy Duration Threshold (s)", anchor="w").pack(side="left", padx=(4,6))
        self.drowsy_val_lbl = ctk.CTkLabel(drow, text="5s", width=60); self.drowsy_val_lbl.pack(side="right", padx=(6,4))
        self.drowsy_time_slider = ctk.CTkSlider(status, from_=3, to=30, command=lambda v: self._on_slider_change("drowsy", v)); self.drowsy_time_slider.set(5); self.drowsy_time_slider.pack(fill="x", pady=(0,6))

        crow = ctk.CTkFrame(status); crow.pack(fill="x", pady=(6,2))
        ctk.CTkLabel(crow, text="Detection Confidence", anchor="w").pack(side="left", padx=(4,6))
        self.conf_val_lbl = ctk.CTkLabel(crow, text="0.40", width=60); self.conf_val_lbl.pack(side="right", padx=(6,4))
        self.conf_slider = ctk.CTkSlider(status, from_=0.1, to=0.9, command=lambda v: self._on_slider_change("conf", v)); self.conf_slider.set(0.4); self.conf_slider.pack(fill="x", pady=(0,6))

        zrow = ctk.CTkFrame(status); zrow.pack(fill="x", pady=(6,2))
        ctk.CTkLabel(zrow, text="Video Display Zoom (%)", anchor="w").pack(side="left", padx=(4,6))
        self.zoom_val_lbl = ctk.CTkLabel(zrow, text="100%", width=60); self.zoom_val_lbl.pack(side="right", padx=(6,4))
        self.video_size_slider = ctk.CTkSlider(status, from_=0.5, to=1.5, command=lambda v: self._on_slider_change("zoom", v)); self.video_size_slider.set(1.0); self.video_size_slider.pack(fill="x", pady=(0,6))

        # prepare controllers that need video_panel (flash & break timer)
        # FlashController expects: (container_widget, video_widget, parent_after=callable)
        self.flash = FlashController(self.video_panel, self.video_label, parent_after=self.after)
        self.break_timer = BreakTimer(parent_after=self.after, callback_on_update=self._break_update_cb, show_modal_fn=self._show_break_modal)

        # rolling alertness samples deque for session
        self._alert_samples = deque()
        self._alert_times = deque()

    def _on_slider_change(self, name, val):
        try:
            v = float(val)
        except Exception:
            try:
                v = float(val.get())
            except Exception:
                return
        if name == "drowsy":
            self.drowsy_val_lbl.configure(text=f"{int(round(v))}s")
        elif name == "conf":
            self.conf_val_lbl.configure(text=f"{v:.2f}")
        elif name == "zoom":
            pct = int(round(v * 100)); self.zoom_val_lbl.configure(text=f"{pct}%")

    # -------- controls ----------
    def start_detection(self):
        if self.detection_enabled:
            return
        # open camera
        try:
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(0)
            if not self.cap.isOpened():
                raise RuntimeError("Cannot open webcam.")
        except Exception as e:
            CTkMessagebox(self, "Camera Error", str(e)); return

        # log file
        self.log_file = logmod.create_log_file(self.log_dir, self.start_timestamp, header=self.log_header)
        self.detection_enabled = True; self.paused = False
        self.btn_start.configure(state="disabled"); self.btn_pause.configure(state="normal"); self.btn_stop.configure(state="normal")
        logmod.append_log_event(self.log_file, "Trip_Start", "Detection started.")

        # reset per-second sampler so first sample is immediate
        self._last_state_sample_ts = 0.0

        # start helper loops
        try: self.flash.start_loop(lambda: getattr(self, "_last_frame_for_brightness", None))
        except Exception: pass
        try: self.start_flash_if_night()
        except Exception: pass
        try: self.break_timer.start()
        except Exception: pass

        self._schedule_frame()

    def pause_detection(self):
        self.paused = not self.paused
        self.btn_pause.configure(text="Resume" if self.paused else "Pause")

    def on_stop(self):
        # flush streaks
        try: self.detector.stop_and_flush_streak()
        except Exception: pass

        self.detection_enabled = False; self.paused = True
        self._cleanup_resources()
        try: logmod.append_log_event(self.log_file, "Trip_End", "System disengaged.")
        except Exception: pass

        try:
            report_path = logmod.generate_report(self.report_dir, self.start_timestamp, self.log_file,
                                                 self.detector.yawn_warning_count, self.detector.drowsy_warning_count, self.start_time)
        except Exception:
            report_path = "(report error)"
        try:
            CTkMessagebox(self, "Report Saved", f"Report saved to:\n{report_path}")
        except Exception:
            pass

        # compute metrics and callback
        metrics = self.detector.compute_fatigue_metrics(alert_samples_deque=self._alert_samples)
        try:
            if self.on_dashboard: self.on_dashboard(metrics)
        except Exception:
            pass

        self.btn_start.configure(state="normal"); self.btn_pause.configure(state="disabled", text="Pause"); self.btn_stop.configure(state="disabled")
        try: self.status_label.configure(text="STATUS: stopped")
        except Exception: pass

    def _cleanup_resources(self):
        try:
            if getattr(self, "cap", None) and self.cap.isOpened():
                self.cap.release(); self.cap = None
        except Exception:
            pass
        try:
            import pygame
            if pygame and pygame.mixer.get_init(): pygame.mixer.quit()
        except Exception:
            pass
        try: self.flash.stop_loop()
        except Exception: pass
        try: self.break_timer.stop()
        except Exception: pass

    # ---------- frame loop ----------
    def _schedule_frame(self):
        self.parent.after(30, self.update_frame)

    def update_frame(self):
        if not self.detection_enabled:
            return
        if self.paused:
            self._schedule_frame(); return
        if not getattr(self, "cap", None) or not self.cap.isOpened():
            CTkMessagebox(self, "Camera Error", "Camera is not open."); return

        ret, frame = self.cap.read()
        if not ret:
            self._schedule_frame(); return

        # scale
        try: scale = float(self.video_size_slider.get())
        except Exception: scale = 1.0
        self.video_width = max(1, int(self.base_video_width * scale)); self.video_height = max(1, int(self.base_video_height * scale))
        try:
            frame = cv2.resize(frame, (self.video_width, self.video_height))
        except Exception:
            frame = cv2.resize(frame, (self.base_video_width, self.base_video_height))

        self._last_frame_for_brightness = frame.copy() if frame is not None else None

        # preprocess
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        eq = cv2.equalizeHist(gray)
        proc = cv2.cvtColor(eq, cv2.COLOR_GRAY2BGR)

        try:
            conf_threshold = float(self.conf_slider.get())
        except Exception:
            conf_threshold = 0.4

        # run detector
        status, best_box, detections = self.detector.analyze_frame(proc, conf_threshold=conf_threshold)

        # --- per-second state logging (write EventType="State", Details=<status>) ---
        try:
            now_ts = time.time()
            if self.log_file and (now_ts - getattr(self, "_last_state_sample_ts", 0.0) >= 1.0):
                try:
                    logmod.append_state_sample(self.log_file, status)
                except Exception:
                    pass
                self._last_state_sample_ts = now_ts
        except Exception:
            pass
        # --- end per-second logging ---

        # draw box if available
        if best_box:
            try:
                x1, y1, x2, y2 = map(int, best_box.xyxy[0])
                color = (0,255,0)
                if status == "drowsy": color = (0,0,255)
                elif status == "yawn": color = (0,255,255)
                cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
                try:
                    conf = None
                    try:
                        conf = float(best_box.conf[0])
                    except Exception:
                        try:
                            conf = float(best_box.conf)
                        except Exception:
                            conf = None
                    if conf is not None:
                        cv2.putText(frame, f"{status} {conf:.2f}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                except Exception:
                    pass
            except Exception:
                pass

        # apply detector logic mutations & get actions
        yawn_res = self.detector.handle_yawn_logic(status, log_file=self.log_file)
        drowsy_res = self.detector.handle_drowsy_logic(status, drowsy_limit=int(self.drowsy_time_slider.get()), log_file=self.log_file)

        # handle sounds/logs/popups triggered by detector logic
        try:
            if yawn_res.get("log_entry"):
                k, v = yawn_res["log_entry"]
                logmod.append_log_event(self.log_file, k, v)
            if yawn_res.get("play_sound") and self.detector.yawn_warn_sound:
                try: self.detector.yawn_warn_sound.play(loops=2)
                except Exception: pass
            if yawn_res.get("popup"):
                # simple overlay: set internal flag and let UI draw overlay
                self._show_warning_card("WARNING: HIGH YAWN RATE", "Multiple yawns detected. Consider a short rest.", duration=6)
        except Exception:
            pass

        try:
            if drowsy_res.get("log_entry"):
                k, v = drowsy_res["log_entry"]
                logmod.append_log_event(self.log_file, k, v)
            if drowsy_res.get("play_sound") and self.detector.drowsy_warn_sound:
                try: self.detector.drowsy_warn_sound.play(loops=-1)
                except Exception: pass
            if drowsy_res.get("alert"):
                # after 1s gap, show stronger overlay (we already used detector flags)
                self.after(1000, lambda: self._show_warning_card("WARNING: DROWSINESS", "Prolonged eye-closure detected. Pull over and rest.", duration=8))
        except Exception:
            pass

        # overlay for yawn popup (drawn on frame)
        if getattr(self, "yawn_popup_active", False):
            overlay = frame.copy()
            alpha = 0.8
            box_color = (40,40,40) if ctk.get_appearance_mode()=="Dark" else (230,230,230)
            title_color = (255,255,0) if ctk.get_appearance_mode()=="Dark" else (200,0,0)
            cv2.rectangle(overlay, (50,100), (self.video_width-50,300), box_color, -1)
            cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0, frame)
            cv2.rectangle(frame, (50,100), (self.video_width-50,300), title_color, 2)
            (tw, th), _ = cv2.getTextSize("WARNING: HIGH DROWSINESS TENDENCY", cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.putText(frame, "WARNING: HIGH DROWSINESS TENDENCY", (int((self.video_width-tw)/2), 150), cv2.FONT_HERSHEY_SIMPLEX, 0.7, title_color, 2)
            cv2.putText(frame, "Please pull over and take a break.", (int((self.video_width-300)/2), 200), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
            if time.time() - getattr(self, "yawn_popup_start_time", 0) > 6:
                self.yawn_popup_active = False
                self.detector.yawn_count = 0
                try:
                    if self.detector.yawn_warn_sound:
                        self.detector.yawn_warn_sound.stop()
                except Exception:
                    pass

        # convert to CTkImage and display
        try:
            cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            img = Image.fromarray(cv2image)
            imgtk = ctk.CTkImage(light_image=img, dark_image=img, size=(self.video_width, self.video_height))
            self.video_label.configure(image=imgtk, text="")
        except Exception:
            self.video_label.configure(text="Frame captured")

        # update rolling alertness
        try:
            now = time.time()
            is_drowsy = (status == "drowsy")
            self._alert_samples.append(is_drowsy)
            self._alert_times.append(now)
            while self._alert_times and (now - self._alert_times[0]) > self.ALERT_WINDOW_S:
                self._alert_times.popleft(); self._alert_samples.popleft()
            total = max(1, len(self._alert_samples)); dcount = sum(1 for v in self._alert_samples if v)
            alertness = max(0.0, 100.0 * (1.0 - (dcount / float(total))))
            try:
                self.alertness_bar.set(alertness/100.0)
                self.alertness_val_lbl.configure(text=f"{int(round(alertness))}%")
            except Exception:
                pass
            if self.on_alertness:
                try: self.on_alertness(float(alertness))
                except Exception:
                    pass
        except Exception:
            pass

        # update status labels
        try:
            self.status_label.configure(text=f"STATUS: {status.upper()}")
            self.yawn_label.configure(text=f"Yawn Count: {self.detector.yawn_count}")
            drowsy_timer_text = "Drowsy Timer: 0s"
            if self.detector.drowsy_start_time is not None:
                drowsy_timer_text = f"Drowsy Timer: {int(time.time() - self.detector.drowsy_start_time)}s"
            self.drowsy_timer_label.configure(text=drowsy_timer_text)
        except Exception:
            pass

        self._schedule_frame()

    # ---------- overlays ----------
    def _show_warning_card(self, title, message, duration=6):
        # create a Toplevel overlay centered on video_panel (simple)
        try:
            if getattr(self, "_warning_card", None):
                # refresh text and extend duration
                try:
                    self._warning_title.config(text=title); self._warning_msg.config(text=message)
                except Exception:
                    pass
                if getattr(self, "_warning_cancel_job", None):
                    try: self.after_cancel(self._warning_cancel_job)
                    except Exception: pass
                self._warning_cancel_job = self.after(int(duration*1000), self._hide_warning_card)
                return
        except Exception:
            pass

        try:
            vp = self.video_panel
            x = vp.winfo_rootx(); y = vp.winfo_rooty(); w = vp.winfo_width(); h = vp.winfo_height()
            if w <= 10 or h <= 10:
                w = self.video_width; h = self.video_height; x = self.winfo_rootx()+20; y = self.winfo_rooty()+60
            pw = int(w * 0.6); ph = int(h * 0.22); px = x + (w - pw)//2; py = y + (h - ph)//2
        except Exception:
            pw = 600; ph = 140; px = py = 100

        top = ctk.CTkToplevel(self); top.overrideredirect(True); top.geometry(f"{pw}x{ph}+{px}+{py}")
        frame = ctk.CTkFrame(top, corner_radius=8)
        frame.pack(fill="both", expand=True)
        self._warning_title = ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=14, weight="bold"))
        self._warning_title.pack(pady=(12,4))
        self._warning_msg = ctk.CTkLabel(frame, text=message, wraplength=pw-40)
        self._warning_msg.pack(pady=(0,8))
        self._warning_card = top
        self._warning_cancel_job = self.after(int(duration*1000), self._hide_warning_card)

    def _hide_warning_card(self):
        try:
            if getattr(self, "_warning_card", None):
                try: self._warning_card.destroy()
                except Exception: pass
                self._warning_card = None
            if getattr(self, "_warning_cancel_job", None):
                try: self.after_cancel(self._warning_cancel_job)
                except Exception: pass
                self._warning_cancel_job = None
        except Exception:
            pass

    # break timer callbacks & modal
    def _break_update_cb(self, payload):
        try:
            if self.on_break_update:
                self.on_break_update(payload)
        except Exception:
            pass

    def _show_break_modal(self, brief=False):
        try:
            msg = "More than an hour driving — consider a short rest." if brief else "Please take a break now."
            dlg = BreakReminderDialog(self.parent, title="Break Reminder", message=msg)
            self.parent.wait_window(dlg)
            res = getattr(dlg, "result", None)
            if res == "break":
                try: self.on_stop()
                except Exception: pass
            elif res == "snooze":
                self.break_timer.snooze(15)
            elif res == "dismiss":
                try: logmod.append_log_event(self.log_file, "Break_Dismissed", f"Dismissed at {datetime.now().isoformat()}")
                except Exception: pass
            self.break_timer._start = time.time()
        except Exception:
            pass

    # ---------- Flash API exposed to launcher ----------
    def start_flash_if_night(self):
        """Start flash if current time is within night hours."""
        if not getattr(config, "FLASH_ENABLED", False):
            return
        now = datetime.now()
        start = getattr(config, "FLASH_NIGHT_START", 18)
        end = getattr(config, "FLASH_NIGHT_END", 6)
        end_min = getattr(config, "FLASH_NIGHT_END_MIN", 0)
        h = now.hour; m = now.minute
        # night if hour >= start OR hour < end (the next day) OR hour == end and minute < end_min
        if (h >= start) or (h < end) or (h == end and m < end_min):
            # use color cycle
            try:
                c1 = getattr(config, "FLASH_COLOR_1", "#ff3333")
                c2 = getattr(config, "FLASH_COLOR_2", "#ffd100")
                ramp = getattr(config, "FLASH_RAMP_SECONDS", 5.0)
                self.flash.start_color_cycle(colors=[c1, c2], ramp_seconds=ramp)
            except Exception:
                pass

    def demo_flash(self, duration=10.0):
        """Demonstrate flash effect for a short time."""
        try:
            c1 = getattr(config, "FLASH_COLOR_1", "#ff3333")
            c2 = getattr(config, "FLASH_COLOR_2", "#ffd100")
            ramp = getattr(config, "FLASH_RAMP_SECONDS", 5.0)
            self.flash.start_color_cycle(colors=[c1, c2], ramp_seconds=ramp)
            self.after(int(duration*1000), lambda: self.flash.stop_loop())
        except Exception:
            pass

    def set_flash_color(self, hex_color):
        """Set flash primary color (user-chosen)."""
        try:
            self.flash.set_color(hex_color)
        except Exception:
            pass

    def stop_flash(self):
        try:
            self.flash.stop_loop()
        except Exception:
            pass


    def toggle_flash(self):
        try:
            if hasattr(self, 'flash') and self.flash:
                # If flash is running, stop; otherwise start if within night hours
                if getattr(self.flash, '_cycle_running', False):
                    try:
                        self.flash.stop_loop()
                        if hasattr(self, 'btn_flash_toggle'):
                            self.btn_flash_toggle.configure(text='Resume Flashing')
                    except Exception:
                        pass
                else:
                    try:
                        # start flash if night (reuse existing start function)
                        self.start_flash_if_night()
                        if hasattr(self, 'btn_flash_toggle'):
                            self.btn_flash_toggle.configure(text='Pause Flashing')
                    except Exception:
                        pass
        except Exception:
            pass


    # --- UI helper methods for right-side panel ---
    def reset_yawn_counter_ui(self):
        try:
            if hasattr(self, 'detector') and self.detector:
                try:
                    self.detector.reset_yawn_counter()
                except Exception:
                    # fallback: set variables directly
                    self.detector.yawn_count = 0
                    self.detector.yawn_warning_count = 0
            self.show_message('Yawn', 'Yawn counter reset.')
        except Exception:
            pass

    def apply_drowsy_threshold(self):
        try:
            val = self.entry_drowsy_threshold.get().strip()
            if not val:
                self.show_message('Threshold', 'Please enter a threshold in seconds.')
                return
            sec = float(val)
            if hasattr(self, 'detector') and self.detector:
                try:
                    self.detector.set_drowsy_alert_threshold(sec)
                except Exception:
                    self.detector.drowsy_alert_threshold = sec
            self.show_message('Threshold', f'Applied drowsy threshold: {sec}s')
        except Exception as e:
            self.show_message('Threshold', f'Failed to apply: {e}')

    def apply_confidence(self):
        try:
            val = self.entry_confidence.get().strip()
            if not val:
                self.show_message('Confidence', 'Please enter a confidence between 0 and 1.')
                return
            c = float(val)
            # ensure slider exists and set default in detector if applicable
            if hasattr(self, 'detector') and self.detector:
                self.detector.confidence_threshold = c
            self.show_message('Confidence', f'Set detection confidence to {c}')
        except Exception as e:
            self.show_message('Confidence', f'Failed: {e}')


    def show_message(self, title, text):
        try:
            import tkinter.messagebox as mb
            mb.showinfo(title, text)
        except Exception:
            pass

    def test_location_ui(self):
        try:
            lat, lon, loc_text = get_ip_location()
            if lat is not None and lon is not None:
                self.show_message('Location', f'Lat: {lat}\nLon: {lon}\n{loc_text}')
            else:
                self.show_message('Location', f'Location unknown. Info: {loc_text}')
        except Exception as e:
            self.show_message('Location', f'Failed to get location: {e}')
