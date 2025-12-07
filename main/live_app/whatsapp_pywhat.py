# live_app/whatsapp_pywhat.py
import os
import json
import time
import traceback
from datetime import datetime

# pywhatkit used to open WhatsApp Web and send messages
try:
    import pywhatkit
except Exception:
    pywhatkit = None

import requests

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SETTINGS_PATH = os.path.join(BASE_DIR, "user_settings.json")

# Defaults
DEFAULT_WAIT_TIME = 10
DEFAULT_CLOSE_TIME = 3
IPINFO_URL = "https://ipinfo.io/json"

def load_user_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"user_name": "", "emergency_whatsapp": ""}

def save_user_settings(settings: dict):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass

def get_ip_location():
    """
    Best-effort IP geolocation via ipinfo.io. Returns (lat, lon, place_str) or (None,None,None).
    """
    try:
        r = requests.get(IPINFO_URL, timeout=6)
        if r.status_code != 200:
            return None, None, None
        d = r.json()
        loc = d.get("loc")
        place = ", ".join([p for p in (d.get("city",""), d.get("region",""), d.get("country","")) if p])
        if loc:
            lat, lon = loc.split(",")
            return float(lat), float(lon), place
    except Exception:
        pass
    return None, None, None

def _normalize_number_for_pywhatkit(number: str):
    if not number:
        return None
    s = str(number).strip()
    s = s.replace(" ", "").replace("(", "").replace(")", "").replace("-", "")
    if s.startswith("00"):
        s = "+" + s[2:]
    if not s.startswith("+"):
        s = "+" + s
    return s

def _send_once_pywhatkit(number: str, text: str, wait_time=DEFAULT_WAIT_TIME, close_time=DEFAULT_CLOSE_TIME):
    """
    Attempt to send a single message using pywhatkit.sendwhatmsg_instantly.
    Returns (ok:bool, reason:str).
    """
    if pywhatkit is None:
        return False, "pywhatkit_missing"
    num = _normalize_number_for_pywhatkit(number)
    if not num:
        return False, "invalid_number"
    try:
        # sendwhatmsg_instantly expects "+{country}{number}" format (or without + sometimes)
        pywhatkit.sendwhatmsg_instantly(num, text, wait_time=wait_time, tab_close=False, close_time=close_time)
        return True, "sent"
    except Exception as e:
        return False, f"error:{e}"

def send_single_alert(number: str, user_name: str, seconds_drowsy: int = 0, wait_time=DEFAULT_WAIT_TIME, close_time=DEFAULT_CLOSE_TIME, log_fn=None):
    """
    Send exactly one WhatsApp message containing current approximate location and a note
    that the location is active for DEFAULT_ACTIVE_MIN minutes.
    Returns (ok:bool, reason:str). This function is synchronous (returns after calling pywhatkit).
    """
    try:
        lat, lon, place = get_ip_location()
        base = (f"ALERT: The user {user_name or 'User'} was detected drowsy for {int(seconds_drowsy)} seconds.\n\n"
                "Please check on them and be prepared to contact emergency services if needed.\n")
        if lat is not None and lon is not None:
            maps = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
            body = f"{base}Location: {maps}\n(Approx: {place or 'unknown'})\nLocation active for 15 minutes (approx)."
        else:
            body = base + "\nLocation not available."

        ok, reason = _send_once_pywhatkit(number, body, wait_time=wait_time, close_time=close_time)
        if log_fn:
            try:
                log_fn("WhatsApp_Event", f"single_send to {number}: ok={ok} reason={reason}")
            except Exception:
                pass
        return ok, reason
    except Exception as ex:
        if log_fn:
            try:
                log_fn("WhatsApp_Event", f"exception in single_send: {ex}")
            except Exception:
                pass
        return False, f"exception:{ex}"
