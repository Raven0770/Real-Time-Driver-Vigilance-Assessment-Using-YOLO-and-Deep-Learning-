# app_logs_ctk.py
import os
import customtkinter as ctk
from frames.reports_frame import ReportsFrame
from frames.analytics_frame import AnalyticsFrame
from frames.rawlogs_frame import RawLogsFrame

# Set appearance
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "trip_safety_logs")
REPORT_DIR = os.path.join(SCRIPT_DIR, "trip_reports")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

class LogsViewerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Trip Logs & Reports - CTk Viewer")
        self.geometry("1100x700")

        # Left: notebook with 3 tabs (Reports / Analytics / Raw Logs)
        self.tab_view = ctk.CTkTabview(self, width=400)
        self.tab_view.pack(side="left", fill="both", expand=False, padx=12, pady=12)

        self.tab_view.add("Reports")
        self.tab_view.add("Analytics")
        self.tab_view.add("Raw Logs")

        # instantiate frames inside tabs
        self.reports_frame = ReportsFrame(self.tab_view.tab("Reports"), REPORT_DIR)
        self.reports_frame.pack(fill="both", expand=True, padx=8, pady=8)

        self.analytics_frame = AnalyticsFrame(self.tab_view.tab("Analytics"), LOG_DIR)
        self.analytics_frame.pack(fill="both", expand=True, padx=8, pady=8)

        self.rawlogs_frame = RawLogsFrame(self.tab_view.tab("Raw Logs"), LOG_DIR)
        self.rawlogs_frame.pack(fill="both", expand=True, padx=8, pady=8)

        # Right side: an info / help panel
        self.side_panel = ctk.CTkFrame(self, width=320)
        self.side_panel.pack(side="right", fill="y", padx=12, pady=12)
        self.side_panel.pack_propagate(False)
        lbl = ctk.CTkLabel(self.side_panel, text="Instructions", font=ctk.CTkFont(size=14, weight="bold"))
        lbl.pack(pady=(10, 6))
        info = (
            "• Reports: view generated .txt reports.\n"
            "• Analytics: pick a CSV log and view warning frequency over time.\n"
            "• Raw Logs: view the raw CSV table.\n\n"
            "Files are auto-detected from:\n"
            f"  {REPORT_DIR}\n  {LOG_DIR}\n\n"
            "Tip: sort files by name to show newest first if you used timestamps in filenames."
        )
        info_lbl = ctk.CTkLabel(self.side_panel, text=info, justify="left", wraplength=280)
        info_lbl.pack(padx=8, pady=6)

if __name__ == "__main__":
    app = LogsViewerApp()
    app.mainloop()
