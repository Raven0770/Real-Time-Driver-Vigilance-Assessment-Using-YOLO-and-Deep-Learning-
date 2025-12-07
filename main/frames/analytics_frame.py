# frames/analytics_frame.py
import os
import math
import pandas as pd
import datetime as dt
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from typing import List, Tuple, Dict, Optional

from utils.file_utils import list_log_files
import config

# --- Helper: infer state from a row dictionary / series ---
def infer_state_from_row(row: pd.Series) -> Optional[str]:
    """
    Try to infer one of 'Attentive', 'Yawn', 'Drowsy' from a row.
    Look at several possible fields and match substrings.
    Returns the canonical label or None if unknown.
    """
    candidates = []
    # prefer explicit state-like columns
    for col in ("state", "State", "status", "Status", "EventType", "Event", "Type", "Details"):
        if col in row and pd.notna(row[col]):
            candidates.append(str(row[col]))

    text = " ".join(candidates).lower()

    # mapping rules
    if "drows" in text or "sleep" in text or "doze" in text or "microsleep" in text:
        return "Drowsy"
    if "yawn" in text or "yawning" in text:
        return "Yawn"
    if "attent" in text or "focused" in text:
        return "Attentive"
    if "awake" in text:
        return "Attentive"

    if "attentive" in text:
        return "Attentive"
    return None

# --- Helper: read CSV and return list of (timestamp, state) tuples ---
def extract_state_events_from_csv(path: str, timestamp_cols: List[str] = None) -> List[Tuple[dt.datetime, str]]:
    if timestamp_cols is None:
        timestamp_cols = ["Timestamp", "timestamp", "Time", "time", "ts", "datetime", "DateTime", "Date"]

    events = []
    try:
        df = pd.read_csv(path, dtype=str, low_memory=False)
    except Exception:
        return events

    # find timestamp column
    time_col = None
    for c in timestamp_cols:
        if c in df.columns:
            time_col = c
            break
    if time_col is None:
        for c in df.columns:
            if any(k in c.lower() for k in ("time", "timestamp", "date")):
                time_col = c
                break

    for _, row in df.iterrows():
        ts = None
        if time_col and row.get(time_col) and not pd.isna(row.get(time_col)):
            raw = str(row.get(time_col))
            parse_success = False
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d_%H-%M-%S", "%d-%m-%Y %H:%M:%S",
                        "%m/%d/%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                try:
                    ts = dt.datetime.strptime(raw, fmt)
                    parse_success = True
                    break
                except Exception:
                    pass
            if not parse_success:
                try:
                    ts = pd.to_datetime(raw, errors="coerce")
                    if isinstance(ts, pd.Timestamp) and pd.isna(ts):
                        ts = None
                except Exception:
                    ts = None
        else:
            ts = None

        state = infer_state_from_row(row)
        if state and ts:
            try:
                if isinstance(ts, pd.Timestamp):
                    events.append((ts.to_pydatetime(), state))
                elif isinstance(ts, dt.datetime):
                    events.append((ts, state))
                else:
                    events.append((pd.to_datetime(ts).to_pydatetime(), state))
            except Exception:
                continue

    return events

# --- Helper: aggregate events into time buckets (bucket_seconds granularity) ---
def bucket_state_counts(events: List[Tuple[dt.datetime, str]], bucket_seconds: int = 60) -> Tuple[List[dt.datetime], Dict[str, List[int]]]:
    """
    Aggregate events into contiguous buckets of bucket_seconds.
    Returns list of bucket start datetimes and counts dict with keys 'Attentive','Yawn','Drowsy'.
    """
    if not events:
        return [], {"Attentive": [], "Yawn": [], "Drowsy": []}

    # sort
    events = sorted(events, key=lambda x: x[0])

    # Align start to bucket boundary (floor)
    epoch = events[0][0]
    start = epoch - dt.timedelta(seconds=(epoch.second % bucket_seconds), microseconds=epoch.microsecond)
    end = events[-1][0]
    # ensure last bucket includes last event
    total_seconds = int(math.ceil((end - start).total_seconds())) + 1
    bucket_count = int(math.ceil(total_seconds / float(bucket_seconds)))

    bins = [start + dt.timedelta(seconds=bucket_seconds * i) for i in range(bucket_count + 1)]
    labels = ["Attentive", "Yawn", "Drowsy"]
    counts = {lab: [0] * (len(bins) - 1) for lab in labels}

    for ts, state in events:
        if ts < bins[0]:
            continue
        i = int((ts - bins[0]).total_seconds() // bucket_seconds)
        if i < 0 or i >= (len(bins) - 1):
            continue
        st_norm = state
        if isinstance(st_norm, str) and st_norm.lower() == "awake":
            st_norm = "Attentive"
        # normalize some possible variants
        if isinstance(st_norm, str):
            if st_norm.lower() in ("attentive", "active", "awake"):
                st_norm = "Attentive"
            elif "yawn" in st_norm.lower():
                st_norm = "Yawn"
            elif "drows" in st_norm.lower() or "sleep" in st_norm.lower():
                st_norm = "Drowsy"
        if st_norm not in counts:
            continue
        counts[st_norm][i] += 1

    return bins[:-1], counts

# --- Analytics Frame ---
class AnalyticsFrame(ctk.CTkFrame):
    def __init__(self, parent, log_dir=config.LOG_DIR, bucket_minutes: int = 1):
        """
        By default this constructor will set the UI bucket selector to '1S' (one second).
        The internal bucket used for aggregation is represented in seconds.
        """
        super().__init__(parent)
        self.log_dir = log_dir
        # default bucket seconds -> 1 second for per-second demos
        self.bucket_seconds = 1

        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=8, pady=(8,6))
        ctk.CTkLabel(top, text="Analytics", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")

        controls = ctk.CTkFrame(top)
        controls.pack(side="right")

        # File selector (All Files + each CSV)
        self.file_var = ctk.StringVar(value="All Files")
        files = []
        try:
            files = list_log_files(self.log_dir) or []
        except Exception:
            # fallback: list files in dir
            try:
                files = [f for f in os.listdir(self.log_dir) if f.lower().endswith(".csv")]
            except Exception:
                files = []
        files = [f for f in files if f.lower().endswith(".csv")]
        files_sorted = sorted(files, reverse=True)
        file_options = ["All Files"] + files_sorted
        self.file_combo = ctk.CTkComboBox(controls, values=file_options, variable=self.file_var, width=280, command=self.on_file_change)
        self.file_combo.set("All Files")
        self.file_combo.pack(side="left", padx=(6,4))

        # Checkboxes to select which series to display
        self.show_attentive_var = tk.IntVar(value=1)
        self.show_yawn_var = tk.IntVar(value=1)
        self.show_drowsy_var = tk.IntVar(value=1)

        self.chk_attentive = ctk.CTkCheckBox(controls, text="Active", variable=self.show_attentive_var, command=self.on_toggle_series)
        self.chk_attentive.pack(side="left", padx=(6,4))
        self.chk_yawn = ctk.CTkCheckBox(controls, text="Yawn", variable=self.show_yawn_var, command=self.on_toggle_series)
        self.chk_yawn.pack(side="left", padx=(6,4))
        self.chk_drowsy = ctk.CTkCheckBox(controls, text="Drowsy", variable=self.show_drowsy_var, command=self.on_toggle_series)
        self.chk_drowsy.pack(side="left", padx=(6,4))

        self.refresh_btn = ctk.CTkButton(controls, text="Refresh", width=90, command=self.refresh)
        self.refresh_btn.pack(side="left", padx=(6,4))

        # bucket selector: entries may be seconds (e.g., "1S") or minutes (plain "1" or "5")
        bucket_values = ["1S", "5S", "10S", "30S", "1", "2", "5", "10", "30", "60"]
        self.bucket_combo = ctk.CTkComboBox(controls, values=bucket_values, width=90, command=self.on_bucket_change)
        self.bucket_combo.set("1S")
        self.bucket_combo.pack(side="left", padx=(6,4))
        ctk.CTkLabel(controls, text="bucket").pack(side="left", padx=(4,0))

        # figure area
        self.fig = Figure(figsize=(8,3), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("Driver State Analytics")
        self.ax.set_xlabel("Time")
        self.ax.set_ylabel("Count")
        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True, padx=8, pady=8)

        # footer
        footer = ctk.CTkFrame(self, height=28)
        footer.pack(fill="x", padx=8, pady=(0,8))
        self.status_lbl = ctk.CTkLabel(footer, text="Ready")
        self.status_lbl.pack(side="left", padx=6)

        # initial draw
        self.refresh()

    def on_bucket_change(self, val):
        """
        val is a string like "1S" or "5" (minutes).
        Set internal bucket_seconds accordingly and refresh.
        """
        try:
            if isinstance(val, str) and val.strip().upper().endswith("S"):
                s = int(val.strip()[:-1])
                if s <= 0: s = 1
                self.bucket_seconds = s
            else:
                # treat as minutes
                m = int(str(val).strip())
                if m <= 0: m = 1
                self.bucket_seconds = m * 60
            self.refresh()
        except Exception:
            # ignore invalid and keep previous
            pass

    def on_file_change(self, val):
        try:
            self.refresh()
        except Exception:
            pass

    def on_toggle_series(self):
        self.refresh()

    def refresh(self):
        # clear axes
        self.ax.clear()
        self.ax.set_title("Driver State Analytics")
        self.ax.set_xlabel("Time")
        self.ax.set_ylabel("Count")

        # determine which files to use based on selector
        selected = self.file_var.get() if hasattr(self, "file_var") else "All Files"

        # gather available files using list_log_files
        available = []
        try:
            available = list_log_files(self.log_dir) or []
        except Exception:
            try:
                available = [f for f in os.listdir(self.log_dir) if f.lower().endswith(".csv")]
            except Exception:
                available = []

        available = [f for f in available if f.lower().endswith(".csv")]
        available = sorted(available, reverse=True)

        if selected == "All Files" or not selected:
            files = available
        else:
            if selected in available:
                files = [selected]
            else:
                # if user selected a path-like option, try to match full path
                joined = os.path.join(self.log_dir, selected)
                if os.path.exists(joined):
                    files = [selected]
                else:
                    files = available

        all_events: List[Tuple[dt.datetime, str]] = []
        for f in files:
            # if list_log_files returns full paths, accept them; else join with log_dir
            path = f if os.path.isabs(f) else os.path.join(self.log_dir, f)
            if not os.path.exists(path):
                continue
            try:
                evs = extract_state_events_from_csv(path)
                all_events.extend(evs)
            except Exception:
                continue

        if not all_events:
            self.ax.text(0.5, 0.5, "No state events found in logs.\nEnsure CSVs have a Timestamp column and state/event info.",
                         ha="center", va="center", transform=self.ax.transAxes)
            self.canvas.draw()
            self.status_lbl.configure(text="No data found")
            return

        bins, counts = bucket_state_counts(all_events, bucket_seconds=self.bucket_seconds)
        x = bins

        # Ensure we have the keys and default zero series
        if "Attentive" not in counts:
            counts["Attentive"] = [0] * len(x)
        if "Yawn" not in counts:
            counts["Yawn"] = [0] * len(x)
        if "Drowsy" not in counts:
            counts["Drowsy"] = [0] * len(x)

        # Plot based on checkboxes
        plotted = 0
        try:
            if self.show_attentive_var.get():
                self.ax.plot(x, counts["Attentive"], label="Active", linewidth=2, marker='o')
                plotted += 1
            if self.show_yawn_var.get():
                self.ax.plot(x, counts["Yawn"], label="Yawn", linewidth=2, marker='o')
                plotted += 1
            if self.show_drowsy_var.get():
                self.ax.plot(x, counts["Drowsy"], label="Drowsy", linewidth=2, marker='o')
                plotted += 1
        except Exception:
            # fallback: plot any available series
            for k, series in counts.items():
                self.ax.plot(x, series, label=k, linewidth=2, marker='o')

        if plotted == 0:
            # nothing selected — show a helpful message
            self.ax.text(0.5, 0.5, "No series selected.\nUse checkboxes to choose series to display.",
                         ha="center", va="center", transform=self.ax.transAxes)
            self.canvas.draw()
            self.status_lbl.configure(text=f"No series selected — {len(files)} file(s) loaded")
            return

        # format x-axis nicely: show seconds if bucket_seconds < 60
        try:
            import matplotlib.dates as mdates
            if self.bucket_seconds < 60:
                fmt = mdates.DateFormatter("%H:%M:%S")
            else:
                fmt = mdates.DateFormatter("%H:%M")
            self.ax.xaxis.set_major_formatter(fmt)
            self.fig.autofmt_xdate(rotation=30)
        except Exception:
            pass

        self.ax.legend(loc="upper left")
        self.ax.grid(True, linestyle='--', alpha=0.4)
        self.canvas.draw()
        total_count = sum(sum(v) for v in counts.values())
        self.status_lbl.configure(text=f"Plotted {total_count} events from {len(files)} file(s)")
