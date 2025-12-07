# app_launcher.py
import os
import sys
import subprocess
import time
import threading
import customtkinter as ctk
import tkinter as tk
from tkinter import colorchooser, messagebox
from PIL import Image, ImageTk
import config

# add this alongside other live_app imports
from live_app import tasker_integration as tasker

# WhatsApp helper (uses pywhatkit)
from live_app import whatsapp_pywhat

# Frames and live_app imports
from frames.reports_frame import ReportsFrame
from frames.analytics_frame import AnalyticsFrame
from frames.rawlogs_frame import RawLogsFrame

# import live_app DETECTOR classes
try:
    from live_app.app_core import DrowsinessFrame, DrowsinessApp
    LIVE_APP_AVAILABLE = True
except Exception:
    DrowsinessFrame = None
    DrowsinessApp = None
    LIVE_APP_AVAILABLE = False

# Initialize theme from config (best-effort)
try:
    ctk.set_appearance_mode(config.APPEARANCE_MODE)
    ctk.set_default_color_theme(config.COLOR_THEME)
except Exception:
    pass

def load_icon(path, size=(22,22)):
    try:
        img = Image.open(path).convert("RGBA")
        img = img.resize(size, Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None

class LauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Deep Drowsiness — Dashboard")
        self.geometry("1200x760")
        self.minsize(1000, 650)

        # Top bar with theme toggle
        header = ctk.CTkFrame(self, height=64)
        header.pack(side="top", fill="x", padx=8, pady=(8,6))
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="Deep Drowsiness Dashboard", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=12)

        # theme toggle
        theme_frame = ctk.CTkFrame(header)
        theme_frame.pack(side="right", padx=12)
        self.theme_var = ctk.StringVar(value=ctk.get_appearance_mode())
        self.theme_menu = ctk.CTkComboBox(theme_frame, values=["System", "Dark", "Light"], variable=self.theme_var, width=110, command=self._on_theme_change)
        self.theme_menu.pack(side="right", padx=(6,0))
        ctk.CTkLabel(theme_frame, text="Theme").pack(side="right", padx=(0,6))

        body = ctk.CTkFrame(self)
        body.pack(fill="both", expand=True, padx=12, pady=(6,12))

        # Left navigation rail
        nav = ctk.CTkFrame(body, width=220, corner_radius=12)
        nav.pack(side="left", fill="y", padx=(0,12))
        nav.pack_propagate(False)

        ctk.CTkLabel(nav, text="Deep\nDrowsiness", font=ctk.CTkFont(size=18, weight="bold"), justify="center").pack(pady=(14,6))

        # Buttons - avoid hard-coded colors so they adapt to theme
        self.btn_embed = ctk.CTkButton(nav, text="Embed Detector", width=180, command=self.embed_live_detector)
        self.btn_embed.pack(pady=(6,6), padx=12)

        self.btn_standalone = ctk.CTkButton(nav, text="Run Detector (Window)", width=180, command=self.launch_live_detector)
        self.btn_standalone.pack(pady=(6,6), padx=12)

        self.btn_logs = ctk.CTkButton(nav, text="Logs Viewer", width=180, command=self.show_logs_viewer)
        self.btn_logs.pack(pady=(10,6), padx=12)

        self.btn_logs_new = ctk.CTkButton(nav, text="Open Logs (New Window)", width=180, command=self.open_logs_new_window)
        self.btn_logs_new.pack(pady=(6,6), padx=12)

        ctk.CTkLabel(nav, text="Quick Actions", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(18,6))
        self.btn_export = ctk.CTkButton(nav, text="Export All Logs", width=160, command=self._export_all)
        self.btn_export.pack(pady=(6,12), padx=12)

        # Content frame (center)
        self.content_frame = ctk.CTkFrame(body, corner_radius=12)
        self.content_frame.pack(side="left", fill="both", expand=True, padx=(0,12))
        self.content_frame.pack_propagate(True)

        # Right info panel
        self.info_panel = ctk.CTkFrame(body, width=300, corner_radius=12)
        self.info_panel.pack(side="right", fill="y")
        self.info_panel.pack_propagate(False)
        ctk.CTkLabel(self.info_panel, text="Session", font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(12,6))
        self.status_label = ctk.CTkLabel(self.info_panel, text="Ready")
        self.status_label.pack(pady=(0,8))
        ctk.CTkLabel(self.info_panel, text="Quick Tips", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(10,6))
        ctk.CTkLabel(self.info_panel, text="- Embed Detector to run inside this window.\n- Use Start/Stop controls.\n- Delete logs from Logs Viewer.", wraplength=260, justify="left").pack(padx=8)

        # FLASH controls (safe: they check availability of detector_frame)
        flash_container = ctk.CTkFrame(self.info_panel)
        flash_container.pack(fill="x", pady=(10,6), padx=8)
        ctk.CTkLabel(flash_container, text="Flash Color", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(2,4))
        self.btn_choose_color = ctk.CTkButton(flash_container, text="Choose Color", command=self._choose_flash_color)
        self.btn_choose_color.pack(fill="x", padx=6, pady=(0,6))
        self.btn_demo_flash = ctk.CTkButton(flash_container, text="Demo Flash", command=self._demo_flash)
        self.btn_demo_flash.pack(fill="x", padx=6)

        # WhatsApp Settings button
        self.btn_whatsapp_settings = ctk.CTkButton(flash_container, text="WhatsApp Settings", command=self._open_whatsapp_settings)
        self.btn_whatsapp_settings.pack(fill="x", padx=6, pady=(6,4))

        # Emergency controls (manual send + automated toggle)
        self.btn_emergency_send = ctk.CTkButton(flash_container, text="Emergency Send", fg_color="#d9534f",
                                               hover_color="#c73c3c", command=self._confirm_emergency_send)
        self.btn_emergency_send.pack(fill="x", padx=6, pady=(8,4))

        # Automated emergency toggle: use a tk.BooleanVar bound to the switch
        self._auto_whatsapp_var = tk.BooleanVar(value=True)
        self._auto_whatsapp_switch = ctk.CTkSwitch(flash_container, text="Automated Emergency", onvalue=True, offvalue=False,
                                                  variable=self._auto_whatsapp_var, command=self._on_toggle_auto_whatsapp, width=60)
        self._auto_whatsapp_switch.pack(padx=6, pady=(4,8))

        # placeholders
        self.placeholder = ctk.CTkLabel(self.content_frame, text="Welcome — choose an action on the left", font=ctk.CTkFont(size=14))
        self.placeholder.pack(expand=True)

        # internal refs
        self.logs_ui = None
        self.detector_frame = None
        self._auto_whatsapp_enabled = True

    def _on_theme_change(self, val):
        try:
            ctk.set_appearance_mode(val)
        except Exception:
            pass

    def _clear_content(self):
        for w in list(self.content_frame.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass
        self.logs_ui = None
        self.detector_frame = None

    def _export_all(self):
        self.status_label.configure(text="Export not implemented")

    def launch_live_detector(self):
        runner_script = os.path.join(os.path.dirname(__file__), "live_app", "run.py")
        module_name = "live_app.run"
        live_app_dir = os.path.join(os.path.dirname(__file__), "live_app")
        log_path = os.path.join(live_app_dir, "launcher_log.txt")

        def try_run_and_capture(cmd_list, cwd=None, timeout=1.0):
            try:
                proc = subprocess.Popen(cmd_list, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except Exception as e:
                return None, ("", str(e))
            time.sleep(0.35)
            if proc.poll() is not None:
                try:
                    out, err = proc.communicate(timeout=timeout)
                    return None, (out.decode(errors='ignore') if out else "", err.decode(errors='ignore') if err else "")
                except Exception:
                    return None, ("", "Process exited and output could not be read.")
            return proc, None

        last_errors = []
        if os.path.exists(runner_script):
            proc, err = try_run_and_capture([sys.executable, runner_script], cwd=os.path.dirname(runner_script))
            if proc:
                self.status_label.configure(text="Standalone detector launched (script).")
                return
            else:
                out, errstr = err
                last_errors.append("Script attempt failed:\n" + (errstr or out))
        else:
            last_errors.append("Runner script not found: live_app/run.py")

        proc, err = try_run_and_capture([sys.executable, "-m", module_name], cwd=None)
        if proc:
            self.status_label.configure(text="Standalone detector launched (module).")
            return
        else:
            out, errstr = err
            last_errors.append("Module attempt failed:\n" + (errstr or out))

        try:
            os.makedirs(live_app_dir, exist_ok=True)
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write("=== Launcher attempts failed ===\n\n")
                for i, t in enumerate(last_errors, 1):
                    lf.write(f"Attempt {i}:\n{t}\n\n")
        except Exception:
            pass

        error_text = (
            "Failed to launch standalone detector.\n\n"
            "Likely causes:\n"
            " - live_app/run.py missing or contains an import error\n"
            " - Missing dependencies (ultralytics, opencv-python, pygame, etc.)\n"
            " - Python interpreter mismatch\n\n"
            "Details were written to:\n  " + log_path + "\n\n"
            "Open that file to inspect stdout/stderr for errors."
        )
        try:
            messagebox.showerror("Launch Failed", error_text)
        except Exception:
            print(error_text)
        self.status_label.configure(text="Failed to launch standalone detector. See launcher_log.txt")

    def embed_live_detector(self):
        self._clear_content()

        tab_view = ctk.CTkTabview(self.content_frame)
        tab_view.pack(fill="both", expand=True, padx=8, pady=8)
        tab_view.add("Detector")
        tab_view.add("Logs")

        det_parent = tab_view.tab("Detector")
        card = ctk.CTkFrame(det_parent, corner_radius=12)
        card.pack(fill="both", expand=True, padx=12, pady=12)

        if LIVE_APP_AVAILABLE and DrowsinessFrame is not None:
            try:
                self.detector_frame = DrowsinessFrame(card)
                self.detector_frame.pack(fill="both", expand=True, padx=8, pady=8)
                try:
                    if getattr(self.detector_frame, "start_flash_if_night", None):
                        self.detector_frame.start_flash_if_night()
                except Exception:
                    pass
                self.status_label.configure(text="Detector embedded. Click Start inside Detector tab.")
            except Exception as e:
                ctk.CTkLabel(card, text=f"Failed to create detector frame:\n{e}", wraplength=560).pack(padx=12, pady=12)
                self.status_label.configure(text="Failed to embed detector")
        else:
            ctk.CTkLabel(card, text="Detector package not available (live_app). Run `pip install` or check files.", wraplength=560).pack(padx=16, pady=12)
            self.status_label.configure(text="Detector not available")

        logs_parent = tab_view.tab("Logs")
        nested = ctk.CTkTabview(logs_parent)
        nested.pack(fill="both", expand=True, padx=8, pady=8)
        nested.add("Reports")
        nested.add("Analytics")
        nested.add("Raw Logs")

        ReportsFrame(nested.tab("Reports"), config.REPORT_DIR).pack(fill="both", expand=True, padx=8, pady=8)
        AnalyticsFrame(nested.tab("Analytics"), config.LOG_DIR).pack(fill="both", expand=True, padx=8, pady=8)
        RawLogsFrame(nested.tab("Raw Logs"), config.LOG_DIR).pack(fill="both", expand=True, padx=8, pady=8)

    def show_logs_viewer(self):
        self._clear_content()
        tab_view = ctk.CTkTabview(self.content_frame)
        tab_view.pack(fill="both", expand=True, padx=8, pady=8)
        tab_view.add("Reports")
        tab_view.add("Analytics")
        tab_view.add("Raw Logs")

        self.reports_frame = ReportsFrame(tab_view.tab("Reports"), config.REPORT_DIR)
        self.reports_frame.pack(fill="both", expand=True, padx=8, pady=8)

        self.analytics_frame = AnalyticsFrame(tab_view.tab("Analytics"), config.LOG_DIR)
        self.analytics_frame.pack(fill="both", expand=True, padx=8, pady=8)

        self.rawlogs_frame = RawLogsFrame(tab_view.tab("Raw Logs"), config.LOG_DIR)
        self.rawlogs_frame.pack(fill="both", expand=True, padx=8, pady=8)

        self.logs_ui = (tab_view,)
        self.status_label.configure(text="Logs viewer opened")

    def open_logs_new_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Logs Viewer")
        win.geometry("1000x650")
        tab_view = ctk.CTkTabview(win)
        tab_view.pack(fill="both", expand=True, padx=8, pady=8)
        tab_view.add("Reports")
        tab_view.add("Analytics")
        tab_view.add("Raw Logs")
        ReportsFrame(tab_view.tab("Reports"), config.REPORT_DIR).pack(fill="both", expand=True, padx=8, pady=8)
        AnalyticsFrame(tab_view.tab("Analytics"), config.LOG_DIR).pack(fill="both", expand=True, padx=8, pady=8)
        RawLogsFrame(tab_view.tab("Raw Logs"), config.LOG_DIR).pack(fill="both", expand=True, padx=8, pady=8)
        self.status_label.configure(text="Opened logs window")

    # --- Flash controls ---
    def _choose_flash_color(self):
        try:
            rgb, hx = colorchooser.askcolor()
        except Exception:
            hx = None
        if not hx:
            return
        if self.detector_frame and hasattr(self.detector_frame, "set_flash_color"):
            try:
                self.detector_frame.set_flash_color(hx)
                self.status_label.configure(text=f"Flash color set to {hx}")
                return
            except Exception:
                pass
        messagebox.showinfo("Flash Not Available", "Flash feature is not active in the embedded detector.")

    def _demo_flash(self):
        if self.detector_frame and hasattr(self.detector_frame, "demo_flash"):
            try:
                dur = getattr(config, "FLASH_DEMO_DURATION_S", 10.0)
                self.detector_frame.demo_flash(duration=dur)
                self.status_label.configure(text="Flash demo started")
                return
            except Exception:
                pass
        messagebox.showinfo("Demo Not Available", "Flash demo is not available for the embedded detector.")

    # ---------------------------
    # Emergency confirmation + send
    # ---------------------------
    def _confirm_emergency_send(self):
        """
        Show modal confirmation. If user does not choose in 7 seconds, send automatically.
        """
        try:
            if not hasattr(self, "detector_frame") or self.detector_frame is None:
                try:
                    messagebox.showwarning("No detector", "Detector not embedded — embed detector first to use Emergency Send.")
                except Exception:
                    pass
                return

            dlg = ctk.CTkToplevel(self)
            dlg.title("Confirm Emergency Send")
            dlg.geometry("460x170")
            dlg.transient(self)
            dlg.grab_set()

            ctk.CTkLabel(dlg, text="Send Emergency WhatsApp alert now?", font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(12,8))
            ctk.CTkLabel(dlg, text="If no response within 7 seconds, the message will be sent automatically.", wraplength=420).pack(pady=(0,8))

            btn_frame = ctk.CTkFrame(dlg)
            btn_frame.pack(pady=(6,8))

            def _do_send_and_close():
                try:
                    self._perform_emergency_send()
                finally:
                    try:
                        dlg.destroy()
                    except Exception:
                        pass

            def _cancel_and_close():
                try:
                    if dlg:
                        dlg.destroy()
                except Exception:
                    pass

            yes_btn = ctk.CTkButton(btn_frame, text="Yes — Send", fg_color="#d9534f", hover_color="#c73c3c", command=_do_send_and_close)
            yes_btn.pack(side="left", padx=8)

            no_btn = ctk.CTkButton(btn_frame, text="No — Cancel", fg_color="#888888", hover_color="#666666", command=_cancel_and_close)
            no_btn.pack(side="left", padx=8)

            # Auto-send timer (7 seconds)
            def _auto_send_countdown():
                try:
                    time.sleep(7)
                    if dlg.winfo_exists():
                        try:
                            self.after(50, _do_send_and_close)
                        except Exception:
                            _do_send_and_close()
                except Exception:
                    pass

            t = threading.Thread(target=_auto_send_countdown, daemon=True)
            t.start()

        except Exception:
            pass

    def _perform_emergency_send(self):
        """Perform the actual emergency send using detector.emergency_send() and show result to user."""
        try:
            log_file = getattr(self.detector_frame, "log_file", None)
            ok = False
            try:
                ok = self.detector_frame.emergency_send(log_file=log_file)
            except Exception:
                ok = False

            if ok:
                try:
                    messagebox.showinfo("Emergency Sent", "Emergency message sent (WhatsApp Web opened).")
                except Exception:
                    pass
                self.status_label.configure(text="Emergency send executed")
            else:
                try:
                    messagebox.showwarning("Send Failed", "Emergency send failed — ensure emergency number is configured and WhatsApp Web is available.")
                except Exception:
                    pass
                self.status_label.configure(text="Emergency send failed")
        except Exception:
            pass

    def _on_toggle_auto_whatsapp(self, _=None):
        try:
            enabled = bool(self._auto_whatsapp_var.get())
            self._auto_whatsapp_enabled = enabled
            try:
                if hasattr(self, "detector_frame") and self.detector_frame is not None:
                    self.detector_frame.enable_whatsapp(enabled)
            except Exception:
                pass
            self.status_label.configure(text=f"Automated Emergency {'enabled' if enabled else 'disabled'}")
        except Exception:
            pass

    # ---------------------------
    # WhatsApp Settings modal
    # ---------------------------
    def _open_whatsapp_settings(self):
        """
        Modal dialog to edit / save user_settings.json (user_name, emergency_whatsapp)
        and test-send an alert.
        """
        try:
            settings = whatsapp_pywhat.load_user_settings() if hasattr(whatsapp_pywhat, "load_user_settings") else {"user_name": "", "emergency_whatsapp": ""}
        except Exception:
            settings = {"user_name": "", "emergency_whatsapp": ""}

        dlg = ctk.CTkToplevel(self)
        dlg.title("WhatsApp Settings")
        dlg.geometry("520x260")
        dlg.transient(self)
        dlg.grab_set()

        frm = ctk.CTkFrame(dlg)
        frm.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(frm, text="WhatsApp Emergency Settings", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(0,8))

        row = ctk.CTkFrame(frm)
        row.pack(fill="x", pady=(6,4))
        ctk.CTkLabel(row, text="Your name (optional)", width=140, anchor="w").pack(side="left", padx=(2,6))
        name_var = tk.StringVar(value=settings.get("user_name", ""))
        name_entry = ctk.CTkEntry(row, textvariable=name_var, placeholder_text="e.g. Prasad")
        name_entry.pack(side="left", fill="x", expand=True, padx=(4,2))

        row2 = ctk.CTkFrame(frm)
        row2.pack(fill="x", pady=(6,4))
        ctk.CTkLabel(row2, text="Emergency WhatsApp", width=140, anchor="w").pack(side="left", padx=(2,6))
        phone_var = tk.StringVar(value=settings.get("emergency_whatsapp", ""))
        phone_entry = ctk.CTkEntry(row2, textvariable=phone_var, placeholder_text="+911234567890")
        phone_entry.pack(side="left", fill="x", expand=True, padx=(4,2))

        hint = ctk.CTkLabel(frm, text="Use international format (e.g. +911234567890). Click Test Send to verify WhatsApp Web.", wraplength=480, justify="left")
        hint.pack(pady=(6,6))

        btns = ctk.CTkFrame(frm)
        btns.pack(fill="x", pady=(6,2))
        def _save_settings():
            s = {"user_name": name_var.get().strip(), "emergency_whatsapp": phone_var.get().strip()}
            try:
                whatsapp_pywhat.save_user_settings(s)
                messagebox.showinfo("Saved", "WhatsApp settings saved.")
            except Exception as e:
                messagebox.showwarning("Save Failed", f"Could not save settings: {e}")

        def _do_test_send():
            # basic validation
            num = phone_var.get().strip()
            if not num:
                messagebox.showwarning("No Number", "Please enter emergency WhatsApp number first.")
                return
            # disable dialog buttons briefly
            try:
                test_btn.configure(state="disabled", text="Sending...")
                self.update_idletasks()
                # attempt send (use the same function your tests used)
                ok, reason = whatsapp_pywhat.send_single_alert(number=num, user_name=name_var.get().strip(), seconds_drowsy=0, wait_time=getattr(config, "WHATSAPP_PYWHAT_WAIT_S", 10), close_time=getattr(config, "WHATSAPP_PYWHAT_CLOSE_S", 3))
                if ok:
                    messagebox.showinfo("Test Sent", "Test message started — WhatsApp Web will open. Ensure you are logged in.")
                else:
                    messagebox.showwarning("Test Failed", f"Test send failed (reason: {reason}).\nMake sure WhatsApp Web is logged in and the number is correct.")
            except Exception as e:
                messagebox.showwarning("Test Error", f"Exception while sending test: {e}")
            finally:
                try:
                    test_btn.configure(state="normal", text="Test Send")
                except Exception:
                    pass

        save_btn = ctk.CTkButton(btns, text="Save", command=_save_settings)
        save_btn.pack(side="left", padx=(6,8))

        test_btn = ctk.CTkButton(btns, text="Test Send", fg_color="#2d8cf0", command=_do_test_send)
        test_btn.pack(side="left", padx=(6,8))

        close_btn = ctk.CTkButton(btns, text="Close", fg_color="#888", command=dlg.destroy)
        close_btn.pack(side="right", padx=(6,8))


# ----------------------------------------------------------
# Robust startup block: create GUI, capture unexpected trace
# ----------------------------------------------------------
if __name__ == "__main__":
    import traceback
    trace_path = os.path.join(os.path.dirname(__file__), "live_app", "launcher_traceback.txt")
    try:
        app = LauncherApp()
        app.mainloop()
    except Exception:
        tb = traceback.format_exc()
        try:
            os.makedirs(os.path.join(os.path.dirname(__file__), "live_app"), exist_ok=True)
            with open(trace_path, "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass
        print("Fatal error starting LauncherApp. Traceback written to:", trace_path, file=sys.stderr)
        print(tb, file=sys.stderr)
        try:
            root = tk.Tk(); root.withdraw()
            tk.messagebox.showerror("Launch Failed", "Launcher failed to start. See file:\n" + trace_path)
            root.destroy()
        except Exception:
            pass
        sys.exit(2)
