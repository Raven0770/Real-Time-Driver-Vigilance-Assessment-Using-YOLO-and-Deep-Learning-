# live_app/logger.py
import csv
import os
import time
from datetime import datetime
from typing import Optional, List

def create_log_file(log_dir: str, start_timestamp: str, header: List[str] = None) -> str:
    """
    Create a CSV log file with a header. Default header includes Timestamp, EventType, Details.
    Returns full path.
    """
    header = header or ['Timestamp', 'EventType', 'Details']
    os.makedirs(log_dir, exist_ok=True)
    log_filename = f"Trip_Log_{start_timestamp}.csv"
    path = os.path.join(log_dir, log_filename)
    try:
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header)
    except Exception:
        # fallback without specifying encoding
        try:
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(header)
        except Exception:
            pass
    return path

def append_log_event(log_file: Optional[str], event_type: str, details: str = ""):
    """
    Append a single event row. Use for occasional events (start/end/warnings).
    """
    if not log_file:
        return
    try:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([ts, event_type, details])
    except Exception:
        try:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([ts, event_type, details])
        except Exception:
            pass

def append_state_sample(log_file: Optional[str], state: str):
    """
    Append a per-second state sample to the CSV log.
    Writes a row with: Timestamp, EventType='State', Details=<state>.
    Designed to be cheap and resilient when called at ~1Hz from the detection loop.
    """
    if not log_file:
        return
    try:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([ts, "State", state])
    except Exception:
        try:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([ts, "State", state])
        except Exception:
            pass

def generate_report(report_dir: str, report_filename_prefix: str, log_file: Optional[str],
                    yawn_warning_count: int, drowsy_warning_count: int, start_time: float) -> str:
    """
    Create a textual trip report and return its path.
    """
    os.makedirs(report_dir, exist_ok=True)
    start_ts = report_filename_prefix
    report_filename = f"Trip_Report_{start_ts}.txt"
    report_path = os.path.join(report_dir, report_filename)

    total_time_min = (time.time() - start_time) / 60.0 if start_time else 0.0
    safety_score = max(0, 100 - (yawn_warning_count * 5) - (drowsy_warning_count * 10))

    report_str = (
        f"\n{'='*30}\n"
        f"     TRIP SAFETY REPORT\n"
        f"{'='*30}\n"
        f"Total Drive Time: {total_time_min:.2f} minutes\n"
        f"Final Driver Safety Score: {safety_score}/100\n\n"
        f"--- Total Incidents Logged ---\n"
        f"  - Yawn Warnings: {yawn_warning_count}\n"
        f"  - Drowsy Warnings: {drowsy_warning_count}\n\n"
        f"Full event log saved to: {log_file}\n"
        f"{'='*30}\n"
    )

    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_str.replace("="*30, "-"*30))
            f.write("\n--- Full Event Log ---\n")
            if log_file and os.path.exists(log_file):
                try:
                    with open(log_file, 'r', encoding='utf-8') as csv_file:
                        f.write(csv_file.read())
                except Exception:
                    try:
                        with open(log_file, 'r') as csv_file:
                            f.write(csv_file.read())
                    except Exception:
                        f.write("Could not read log file contents.\n")
        return report_path
    except Exception:
        return ""
