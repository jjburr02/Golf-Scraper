# --- keep this path bootstrap at the very top ---
import os, sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
# -------------------------------------------------

import asyncio, random, re, traceback
from datetime import datetime, timedelta, date
import aiohttp
from dotenv import load_dotenv
import pytz
import smtplib
from email.mime.text import MIMEText

from providers.lightspeed import parse_lightspeed_html
from providers.generic_html import parse_generic_html
from storage import state as state_store

load_dotenv()

# ---- App settings ----
TIMEZONE = os.getenv("TIMEZONE", "America/Denver")
TZ = pytz.timezone(TIMEZONE)

POLL_SECONDS = int(os.getenv("POLL_SECONDS", "600"))
JITTER_SECONDS = int(os.getenv("JITTER_SECONDS", "30"))

# ---- Email configuration ----
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")   # e.g., yourgmail@gmail.com
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")   # e.g., Gmail App Password
EMAIL_TO = "jjburr@bu.edu"                   # destination email
EMAIL_FROM = SMTP_USERNAME                   # sender (same as your SMTP username)

# Fail fast if creds missing
if not (SMTP_USERNAME and SMTP_PASSWORD):
    raise RuntimeError(
        "Missing SMTP_USERNAME/SMTP_PASSWORD. For Gmail, enable 2FA and use an App Password."
    )

# ---- Courses to monitor (use actual tee-sheet URLs when possible) ----
COURSE_SOURCES = [
    {"name": "Bonneville",    "provider": "lightspeed_web", "url": "https://slc-golf.com/bonneville/",_
