# live_app/tasker_integration.py
"""
Tasker integration helper.

This module is intentionally lightweight:
- Reads TASKER_WEBHOOK_URL from config.py
- Provides trigger_tasker() (synchronous) and trigger_tasker_async() (non-blocking)
- Logs events via logger.append_log_event when a log_file is provided.

Usage:
    from live_app import tasker_integration as tasker
    tasker.trigger_tasker_async(log_file=log_file)
"""

import time
import threading
import requests
import config
from . import logger as logmod

_DEFAULT_TIMEOUT = 3  # seconds


def trigger_tasker(log_file: str = None, timeout: int = _DEFAULT_TIMEOUT) -> bool:
    """
    Trigger the Tasker webhook (synchronous).
    Returns True if request succeeded (HTTP 2xx), else False.

    - Reads config.TASKER_WEBHOOK_URL (string). If empty / not set -> returns False.
    - Sends GET request to the webhook URL.
    - Logs an event to log_file if provided and logger.append_log_event exists.
    """
    try:
        url = getattr(config, "TASKER_WEBHOOK_URL", None)
        if not url:
            if log_file and hasattr(logmod, "append_log_event"):
                logmod.append_log_event(log_file, "Tasker_Skipped", "No TASKER_WEBHOOK_URL configured.")
            return False

        # Ensure scheme is present
        if not url.lower().startswith(("http://", "https://")):
            if log_file and hasattr(logmod, "append_log_event"):
                logmod.append_log_event(log_file, "Tasker_Error", f"Invalid Tasker URL: {url}")
            return False

        # Make GET request
        resp = requests.get(url, timeout=timeout)
        ok = 200 <= resp.status_code < 300
        if log_file and hasattr(logmod, "append_log_event"):
            logmod.append_log_event(log_file, "Tasker_Trigger", f"URL={url} status={resp.status_code} ok={ok}")
        return ok
    except Exception as e:
        if log_file and hasattr(logmod, "append_log_event"):
            logmod.append_log_event(log_file, "Tasker_Exception", str(e))
        return False


def trigger_tasker_async(log_file: str = None, timeout: int = _DEFAULT_TIMEOUT):
    """Non-blocking wrapper that launches trigger_tasker in a daemon thread."""
    def _worker():
        try:
            trigger_tasker(log_file=log_file, timeout=timeout)
        except Exception:
            # already logged inside trigger_tasker
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return True
