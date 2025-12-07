# live_app/app_core.py
"""
Facade module — exposes DrowsinessFrame and convenience runner (DrowsinessApp).
This file imports from ui.py to preserve the original public API.
"""

from .ui import DrowsinessFrame
import customtkinter as ctk
import config

class DrowsinessApp:
    def __init__(self, title="Drowsiness Detector (Standalone)"):
        try:
            ctk.set_appearance_mode(config.APPEARANCE_MODE)
            ctk.set_default_color_theme(config.COLOR_THEME)
        except Exception:
            pass
        self.window = ctk.CTk()
        self.window.title(title)
        self.window.geometry("980x700")
        self.frame = DrowsinessFrame(self.window)
        self.frame.pack(fill="both", expand=True)
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

    def run(self):
        self.window.mainloop()

    def on_closing(self):
        try:
            if self.frame.detection_enabled:
                self.frame.on_stop()
        except Exception:
            pass
        self.window.destroy()
