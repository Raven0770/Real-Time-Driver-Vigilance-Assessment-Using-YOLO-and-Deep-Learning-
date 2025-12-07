# live_app/run.py
from .app_core import DrowsinessApp

if __name__ == "__main__":
    app = DrowsinessApp("Deep Drowsiness Detector")
    app.run()
