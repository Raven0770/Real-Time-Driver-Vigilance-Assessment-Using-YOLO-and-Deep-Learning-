# utils/file_utils.py
import os
from typing import List

def list_report_files(reports_dir: str) -> List[str]:
    try:
        files = [f for f in os.listdir(reports_dir) if f.lower().endswith(".txt")]
        files.sort(reverse=True)
        return files
    except Exception:
        return []

def list_log_files(log_dir: str) -> List[str]:
    try:
        files = [f for f in os.listdir(log_dir) if f.lower().endswith(".csv")]
        files.sort(reverse=True)
        return files
    except Exception:
        return []

def delete_file(path: str) -> bool:
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
        return False
    except Exception:
        return False
