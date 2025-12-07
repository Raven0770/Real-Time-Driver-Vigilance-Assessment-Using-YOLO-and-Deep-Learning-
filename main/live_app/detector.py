# live_app/detector.py
import os
import time
from urllib.parse import quote
from datetime import datetime

# single-send whatsapp helper
from live_app import whatsapp_pywhat

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

try:
    import pygame
except Exception:
    pygame = None

from . import logger as logmod
import config


class Detector:
    def __init__(self, model_dir=config.MODEL_DIR, sound_dir=config.SOUND_DIR):
        self.model_dir = model_dir
        self.sound_dir = sound_dir

        # WhatsApp state: single-send guard
        self._whatsapp_active_until = 0.0   # epoch seconds until which no new auto-send should occur
        self._whatsapp_enabled = True       # toggle for auto sending

        # model / sounds
        self.model = None
        self.yawn_warn_sound = None
        self.drowsy_warn_sound = None

        # counters & timers
        self.start_time = time.time()
        self.yawn_count = 0
        self.last_yawn_time = 0.0
        self.is_yawning_event = False

        self.drowsy_start_time = None
        self.is_drowsy_alert_playing = False

        # totals
        self.yawn_warning_count = 0
        self.drowsy_warning_count = 0

        # streaks
        self._current_drowsy_streak_start = None
        self.drowsy_streaks = []

        # Yawn warning cooldown (seconds)

        # --- new configurable parameters ---
        # minimum non-drowsy grace (if not drowsy even for this small time, we reset immediately)
        self.drowsy_grace_s = getattr(self, 'drowsy_grace_s', 0.01)
        # alert threshold (seconds) -- can be overridden by UI at runtime
        self.drowsy_alert_threshold = getattr(self, 'drowsy_alert_threshold', 6)
        # expose a flag to allow UI toggling of flashing
        self.flash_enabled_by_ui = True
        self.last_yawn_warning_time = 0.0
        self.yawn_warning_cooldown_s = 2

        # Pending schedule
        self.pending_yawn_time = None
        self.yawn_warning_delay_s = 2

        # load model & sounds (best-effort)
        self._load_model_and_sounds()

    def _load_model_and_sounds(self):
        try:
            model_path = os.path.join(self.model_dir, "final_model.pt")
            if YOLO is None or not os.path.exists(model_path):
                raise FileNotFoundError("YOLO model not available or final_model.pt missing.")
            self.model = YOLO(model_path)
        except Exception:
            self.model = None

        if pygame is not None:
            try:
                pygame.mixer.init()
                yawn_path = os.path.join(self.sound_dir, "yawn_warning.wav")
                drowsy_path = os.path.join(self.sound_dir, "drowsy_warning.wav")
                if os.path.exists(yawn_path):
                    self.yawn_warn_sound = pygame.mixer.Sound(yawn_path)
                if os.path.exists(drowsy_path):
                    self.drowsy_warn_sound = pygame.mixer.Sound(drowsy_path)
                    if self.drowsy_warn_sound:
                        self.drowsy_warn_sound.set_volume(0.5)
            except Exception:
                self.yawn_warn_sound = None
                self.drowsy_warn_sound = None

    def analyze_frame(self, frame, conf_threshold=0.4):
        results = None
        detections = []
        if self.model is not None:
            try:
                results = self.model(frame, conf=conf_threshold, verbose=False)
            except Exception:
                results = None

        status = "attentive"
        best_box = None

        if results:
            try:
                for r in results:
                    for box in r.boxes:
                        cls_idx = int(box.cls[0])
                        cls_name = self.model.names[cls_idx] if hasattr(self.model, "names") else str(cls_idx)
                        detections.append((cls_name, box))
            except Exception:
                detections = []

        yawn_det = next((d for d in detections if d[0] == "yawn"), None)
        drowsy_det = next((d for d in detections if d[0] == "drowsy"), None)

        if yawn_det:
            status = "yawn"; best_box = yawn_det[1]
        elif drowsy_det:
            status = "drowsy"; best_box = drowsy_det[1]
        elif detections:
            att = next((d for d in detections if d[0] == "attentive"), None)
            if att:
                status = "attentive"; best_box = att[1]

        return status, best_box, detections

    def handle_yawn_logic(self, status, log_file=None, threshold=5, delay_seconds=None):
        out = {"popup": False, "play_sound": False, "log_entry": None, "pending": False}
        now = time.time()

        if delay_seconds is not None:
            try:
                dsec = float(delay_seconds)
            except Exception:
                dsec = self.yawn_warning_delay_s
        else:
            dsec = self.yawn_warning_delay_s

        if status == "yawn":
            if not self.is_yawning_event:
                self.is_yawning_event = True
                if now - self.last_yawn_time > 60:
                    self.yawn_count = 1
                else:
                    self.yawn_count += 1
                self.last_yawn_time = now
        else:
            self.is_yawning_event = False

        if self.pending_yawn_time is not None:
            cooldown_ready_time = self.last_yawn_warning_time + self.yawn_warning_cooldown_s
            if self.pending_yawn_time < cooldown_ready_time:
                self.pending_yawn_time = cooldown_ready_time

            if now >= self.pending_yawn_time:
                out["popup"] = True
                out["play_sound"] = bool(self.yawn_warn_sound)
                out["log_entry"] = ("Yawn_Warning", f"{int(threshold)} yawns detected.")
                self.yawn_warning_count += 1
                self.last_yawn_warning_time = now
                self.pending_yawn_time = None
                self.yawn_count = 0
            else:
                out["pending"] = True
            return out

        try:
            thresh = int(threshold)
        except Exception:
            thresh = 5

        if self.yawn_count >= thresh:
            self.pending_yawn_time = now + float(dsec)
            out["pending"] = True
            return out

        return out

    def _send_whatsapp_once_guarded(self, log_file=None, drowsy_duration_s=0):
        """
        Send a single WhatsApp message with approximate location if:
          - _whatsapp_enabled is True
          - now > _whatsapp_active_until
        Sets _whatsapp_active_until = now + WHATSAPP_ACTIVE_WINDOW_MIN*60 on success (or attempt).
        """
        try:
            if not self._whatsapp_enabled:
                if log_file and hasattr(logmod, "append_log_event"):
                    logmod.append_log_event(log_file, "WhatsApp_Event", "auto-send disabled by toggle")
                return False

            now = time.time()
            if now < getattr(self, "_whatsapp_active_until", 0.0):
                # already sent recently
                if log_file and hasattr(logmod, "append_log_event"):
                    logmod.append_log_event(log_file, "WhatsApp_Event", "auto-send suppressed: active window not expired")
                return False

            settings = whatsapp_pywhat.load_user_settings()
            phone = settings.get("emergency_whatsapp", "").strip()
            user_name = settings.get("user_name", "")
            if not phone:
                if log_file and hasattr(logmod, "append_log_event"):
                    logmod.append_log_event(log_file, "WhatsApp_Event", "no phone configured; skipping auto-send")
                return False

            # attempt send (synchronous): will open WhatsApp Web
            wait_time = getattr(config, "WHATSAPP_PYWHAT_WAIT_S", 10)
            close_time = getattr(config, "WHATSAPP_PYWHAT_CLOSE_S", 3)
            ok, reason = whatsapp_pywhat.send_single_alert(number=phone, user_name=user_name, seconds_drowsy=int(drowsy_duration_s), wait_time=wait_time, close_time=close_time, log_fn=(lambda etype, msg: logmod.append_log_event(log_file, etype, msg)) if log_file and hasattr(logmod, "append_log_event") else None)

            # set active window for configured minutes whether the send succeeded or not, to avoid rapid repeats
            active_min = getattr(config, "WHATSAPP_ACTIVE_WINDOW_MIN", 15)
            self._whatsapp_active_until = time.time() + (int(active_min) * 60)
            if log_file and hasattr(logmod, "append_log_event"):
                logmod.append_log_event(log_file, "WhatsApp_Event", f"auto-send attempted to {phone}: ok={ok} reason={reason}; active_until set")
            return ok
        except Exception as ex:
            if log_file and hasattr(logmod, "append_log_event"):
                logmod.append_log_event(log_file, "WhatsApp_Event", f"exception in auto-send: {ex}")
            # still set guard to avoid spam
            active_min = getattr(config, "WHATSAPP_ACTIVE_WINDOW_MIN", 15)
            self._whatsapp_active_until = time.time() + (int(active_min) * 60)
            return False

    def emergency_send(self, log_file=None):
        """
        Manual emergency send triggered by user action (button).
        This will also set the active window to avoid repeated auto sends.
        """
        try:
            settings = whatsapp_pywhat.load_user_settings()
            phone = settings.get("emergency_whatsapp", "").strip()
            user_name = settings.get("user_name", "")
            if not phone:
                if log_file and hasattr(logmod, "append_log_event"):
                    logmod.append_log_event(log_file, "WhatsApp_Event", "manual emergency: no phone configured")
                return False

            wait_time = getattr(config, "WHATSAPP_PYWHAT_WAIT_S", 10)
            close_time = getattr(config, "WHATSAPP_PYWHAT_CLOSE_S", 3)
            ok, reason = whatsapp_pywhat.send_single_alert(number=phone, user_name=user_name, seconds_drowsy=0, wait_time=wait_time, close_time=close_time, log_fn=(lambda etype, msg: logmod.append_log_event(log_file, etype, msg)) if log_file and hasattr(logmod, "append_log_event") else None)
            active_min = getattr(config, "WHATSAPP_ACTIVE_WINDOW_MIN", 15)
            self._whatsapp_active_until = time.time() + (int(active_min) * 60)
            if log_file and hasattr(logmod, "append_log_event"):
                logmod.append_log_event(log_file, "WhatsApp_Event", f"manual_send to {phone}: ok={ok} reason={reason}; active_until set")
            return ok
        except Exception:
            return False

    def enable_whatsapp(self, enabled: bool):
        try:
            self._whatsapp_enabled = bool(enabled)
            return True
        except Exception:
            return False

    def stop_whatsapp_tracking_flag(self):
        try:
            self._whatsapp_active_until = 0.0
            return True
        except Exception:
            return False

    def handle_drowsy_logic(self, status, drowsy_limit, log_file=None):
        out = {"alert": False, "play_sound": False, "log_entry": None}
        try:
            drowsy_limit = int(drowsy_limit)
        except Exception:
            try:
                drowsy_limit = int(float(drowsy_limit))
            except Exception:
                drowsy_limit = 5

        # Use the detector's configured alert threshold (may be updated by UI)
        alert_threshold = getattr(self, 'drowsy_alert_threshold', max(6, drowsy_limit))
        # but ensure minimum sensible floor of 0.01s
        if alert_threshold < 0.01:
            alert_threshold = 0.01
        whatsapp_threshold = 25

        # If status is drowsy, start/continue streak; else, if not drowsy at all, reset immediately
        if status == "drowsy":
            self.alert_start_time = None
            self.alert_grace_start_time = None
            if self.drowsy_start_time is None:
                self.drowsy_start_time = time.time()
                self._current_drowsy_streak_start = time.time()

            dur = time.time() - self.drowsy_start_time

            # start audible alarm at configured threshold
            if dur >= alert_threshold and not self.is_drowsy_alert_playing:
                out["alert"] = True
                out["play_sound"] = bool(self.drowsy_warn_sound)
                out["log_entry"] = ("Drowsy_Warning", f"Drowsy for {alert_threshold}s.")
                self.drowsy_warning_count += 1
                self.is_drowsy_alert_playing = True

            # attempt emergency WhatsApp after sustained duration
            try:
                if dur >= whatsapp_threshold and not getattr(self, "_whatsapp_sent_once", False):
                    self._send_whatsapp_once_guarded(log_file=log_file, drowsy_duration_s=dur)
                    self._whatsapp_sent_once = True
            except Exception:
                pass

        else:
            # If not drowsy even for a tiny period, reset immediately (no gentle grace)
            # Use drowsy_grace_s to allow extremely short flickers if configured
            grace = getattr(self, 'drowsy_grace_s', 0.01)
            if self.drowsy_start_time is not None:
                # If we have been non-drowsy longer than the tiny grace, reset streak
                if self.alert_grace_start_time is None:
                    self.alert_grace_start_time = time.time()
                if time.time() - self.alert_grace_start_time > grace:
                    self.drowsy_start_time = None
                    self.alert_grace_start_time = None
            # stop any playing alert if present
            if self.is_drowsy_alert_playing:
                if self.alert_start_time is None:
                    self.alert_start_time = time.time()
                if time.time() - self.alert_start_time > 2:
                    if self.drowsy_warn_sound:
                        try:
                            self.drowsy_warn_sound.stop()
                        except Exception:
                            pass
                    self.is_drowsy_alert_playing = False
                    self.alert_start_time = None
                    out["log_entry"] = ("Drowsy_Reset", "Driver is attentive.")

            # clear whatsapp sent flag when attentive again
            self._whatsapp_sent_once = False

        return out


    def stop_and_flush_streak(self):
        try:
            if self._current_drowsy_streak_start:
                d = time.time() - self._current_drowsy_streak_start
                if d > 0.5:
                    self.drowsy_streaks.append(d)
                self._current_drowsy_streak_start = None
        except Exception:
            pass

    def compute_fatigue_metrics(self, alert_samples_deque=None):
        try:
            max_d = max(self.drowsy_streaks) if self.drowsy_streaks else 0.0
        except Exception:
            max_d = 0.0
        try:
            samples = list(alert_samples_deque) if alert_samples_deque is not None else []
            avg_alert = 100.0 * (1.0 - (sum(1 for v in samples if v) / float(max(1, len(samples))))) if samples else 100.0
        except Exception:
            avg_alert = 100.0
        if avg_alert < 50 or max_d > 30:
            rec = 20
        elif avg_alert < 70:
            rec = 40
        else:
            rec = 90
        return {
            "max_drowsy_streak_s": int(max_d),
            "avg_alertness_pct": int(round(avg_alert)),
            "recommended_break_min": int(rec),
            "yawn_warnings": self.yawn_warning_count,
            "drowsy_warnings": self.drowsy_warning_count
        }

def get_ip_location(timeout=3):
    """Best-effort IP-based geolocation using ip-api.com. Returns (lat, lon, text) or (None, None, 'Unknown')."""
    try:
        import requests
        resp = requests.get('http://ip-api.com/json/', timeout=timeout)
        if resp.status_code == 200:
            d = resp.json()
            lat = d.get('lat')
            lon = d.get('lon')
            city = d.get('city')
            region = d.get('regionName')
            country = d.get('country')
            isp = d.get('isp')
            text = f"{city or ''}, {region or ''}, {country or ''} (ISP: {isp or ''})"
            return lat, lon, text
    except Exception:
        pass
    return None, None, 'Unknown'




    def reset_yawn_counter(self):
        try:
            self.yawn_count = 0
            self.yawn_warning_count = 0
        except Exception:
            pass


    def set_drowsy_alert_threshold(self, seconds):
        try:
            self.drowsy_alert_threshold = float(seconds)
        except Exception:
            pass
