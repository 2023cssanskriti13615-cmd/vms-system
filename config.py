"""
config.py
Central configuration for the Smart Visitor Management System.

Every value can be overridden with an environment variable, so the same code
runs on a laptop (values come from the .env file) and on Render
(values come from the dashboard's Environment tab).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# When a .env file is present (local development) load it into os.environ.
# On Render there is no .env — the values come from the dashboard instead.
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # the app still runs without python-dotenv installed
    pass


def _get_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    # --- Flask ---------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")

    # --- Database ------------------------------------------------------
    # On Render, set DB_PATH to /var/data/visitors.db and attach a disk
    # if you want records to survive a redeploy.
    DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "visitors.db"))

    # --- Public URL ----------------------------------------------------
    # The QR code must point to a URL the guard's phone can open.
    # Priority: APP_BASE_URL  ->  RENDER_EXTERNAL_URL  ->  current request host
    APP_BASE_URL = os.environ.get("APP_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL")

    # --- Email (Brevo HTTP API) -----------------------------------------
    # Cloud free tiers (Render included) block outbound SMTP ports, so email
    # is sent through Brevo's HTTPS API instead of smtplib. Get a free API
    # key at https://app.brevo.com -> Settings -> SMTP & API -> API Keys.
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")   # the "from" address, must be a verified sender in Brevo
    MAIL_SENDER_NAME = os.environ.get("MAIL_SENDER_NAME", "Visitor Desk")
    # When email is not configured the app still works — the invite link and
    # the pass are shown on screen instead. Useful during a live demo.
    MAIL_ENABLED = bool(BREVO_API_KEY and MAIL_USERNAME)

    # --- Organisation details (shown on the pass) ----------------------
    ORG_NAME = os.environ.get("ORG_NAME", "Visitor Management System")
    ORG_TAGLINE = os.environ.get("ORG_TAGLINE", "Invitation, QR pass and gate verification")

    # --- Default accounts created on first run -------------------------
    EMPLOYEE_USERNAME = os.environ.get("EMPLOYEE_USERNAME", "employee")
    EMPLOYEE_PASSWORD = os.environ.get("EMPLOYEE_PASSWORD", "employee123")
    EMPLOYEE_NAME = os.environ.get("EMPLOYEE_NAME", "Employee Desk")

    GUARD_USERNAME = os.environ.get("GUARD_USERNAME", "guard")
    GUARD_PASSWORD = os.environ.get("GUARD_PASSWORD", "guard123")
    GUARD_NAME = os.environ.get("GUARD_NAME", "Security Officer")