# config.py
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Directories (ensure they exist)
LOG_DIR = os.path.join(SCRIPT_DIR, "trip_safety_logs")
REPORT_DIR = os.path.join(SCRIPT_DIR, "trip_reports")
MODEL_DIR = os.path.join(SCRIPT_DIR, "model")
SOUND_DIR = os.path.join(SCRIPT_DIR, "sounds")

for p in (LOG_DIR, REPORT_DIR, MODEL_DIR, SOUND_DIR):
    os.makedirs(p, exist_ok=True)

# Appearance
# Appearance mode can be "System", "Dark", or "Light"
APPEARANCE_MODE = "System"
# CustomTkinter built-in options: "blue", "green", "dark-blue"
COLOR_THEME = "dark-blue"

# --- Flash settings ---
# Enable/disable automatic flash during night window (18:00 - 06:30)
FLASH_ENABLED = True

# Night start hour (24h) and end hour; if now >= NIGHT_START or now < NIGHT_END => night mode
FLASH_NIGHT_START = 18      # 18 -> 6 PM
FLASH_NIGHT_END = 6         # 6 -> 6 AM (next day)
FLASH_NIGHT_END_MIN = 30    # consider early morning up to 06:30 as night

# Default flash colors (hex)
FLASH_COLOR_1 = "#ff3333"   # red (low/high intensity variation will be simulated by CSS brightness)
FLASH_COLOR_2 = "#ffd100"   # yellow

# Ramp duration for each color (seconds)
FLASH_RAMP_SECONDS = 5.0

# Interval between flash activations while in night mode (seconds)
FLASH_INTERVAL_S = 30.0

# Demo flash duration (seconds)
FLASH_DEMO_DURATION_S = 12.0

# Granularity for animation ticks (ms)
FLASH_TICK_MS = 80

# WhatsApp / pywhatkit behavior
WHATSAPP_PYWHAT_WAIT_S = 10           # pywhatkit wait_time
WHATSAPP_PYWHAT_CLOSE_S = 3           # pywhatkit close_time
WHATSAPP_DROWSY_THRESHOLD_S = 40      # seconds before auto-send triggers
WHATSAPP_ACTIVE_WINDOW_MIN = 15       # minutes to consider "active" after a send (no new auto-sends)


# Optional: Tasker webhook for accurate live location
TASKER_WEBHOOK_URL = "https://tasker.joaoapps.com/api/26/webhook/<YOUR_TASKER_KEY>/trigger/drowsy_alert"
