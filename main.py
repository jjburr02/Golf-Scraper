
import os, sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

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
EMAIL_TO = "jjburr02@gmail.com"                   # destination email
EMAIL_FROM = SMTP_USERNAME                   # sender (same as your SMTP username)

# Fail fast if creds missing
if not (SMTP_USERNAME and SMTP_PASSWORD):
    raise RuntimeError(
        "Missing SMTP_USERNAME/SMTP_PASSWORD. For Gmail, enable 2FA and use an App Password."
    )

# ---- Courses to monitor (use actual tee-sheet URLs when possible) ----
COURSE_SOURCES = [
    {"name": "Bonneville",    "provider": "lightspeed_web", "url": "https://slc-golf.com/bonneville/",     "party_size": 4},
    {"name": "Forest Dale",   "provider": "lightspeed_web", "url": "https://slc-golf.com/forestdale/",     "party_size": 4},
    {"name": "Glendale",      "provider": "lightspeed_web", "url": "https://slc-golf.com/glendale/",       "party_size": 4},
    {"name": "Mountain Dell", "provider": "lightspeed_web", "url": "https://slc-golf.com/mountaindell/",   "party_size": 4},
    {"name": "Nibley Park",   "provider": "lightspeed_web", "url": "https://slc-golf.com/nibley-park/",    "party_size": 4},
    {"name": "Rose Park",     "provider": "lightspeed_web", "url": "https://slc-golf.com/rose-park/",      "party_size": 4},
    {"name": "Old Mill (SLCo)","provider": "lightspeed_web","url": "https://slco.org/parks-recreation/facilities/golf/old-mill/","party_size": 4},
]

MORNING_CUTOFF = (12, 0)  # 12:00 PM local — currently unused, using AM-only check below

# ----------------- Helper Functions -----------------

def next_weekend_dates(today: date | None = None):
    today = today or datetime.now(TZ).date()
    sat = today + timedelta((5 - today.weekday()) % 7)
    sun = sat + timedelta(days=1)
    return [sat, sun]

def parse_target_dates():
    raw = os.getenv("TARGET_DATES", "").strip()
    if not raw:
        return next_weekend_dates()
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        y, m, d = map(int, part.split("-"))
        out.append(date(y, m, d))
    return out

def is_morning(time_str: str) -> bool:
    # Accepts formats like '7:24 AM' or '10:02 AM'
    m = re.match(r"^(\d{1,2}):(\d{2})\s?(AM|PM)$", time_str, re.I)
    if not m:
        return False
    return m.group(3).upper() == "AM"

def capacity_ok(cap) -> bool:
    # If capacity is known, require >= 4; if unknown, allow (conservative)
    return (cap is None) or (cap >= 4)

async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as r:
            r.raise_for_status()
            return await r.text()
    except Exception as e:
        print(f"[fetch_html] Error fetching {url}: {e}")
        return ""

def extract_slots(provider: str, html: str):
    provider = provider.lower()
    items = parse_lightspeed_html(html) if provider == "lightspeed_web" else parse_generic_html(html)
    # Normalize times: "7:24AM" -> "7:24 AM"
    out = []
    for it in items:
        t = (it.get("time_str", "") or "").upper().replace(" ", "")
        t = t.replace("AM", " AM").replace("PM", " PM")
        if not re.match(r"^\d{1,2}:\d{2}\s(AM|PM)$", t):
            continue
        out.append({"time": t, "capacity": it.get("capacity")})
    return out

async def check_course(session, course: dict, target_date: date):
    # NOTE: This fetches the page as-is. Many sites require date selection via query/XHR.
    # For best results, point course['url'] to the actual day-specific tee-sheet page.
    html = await fetch_html(session, course["url"])
    slots = extract_slots(course["provider"], html)
    morning = [s for s in slots if is_morning(s["time"]) and capacity_ok(s["capacity"])]
    return morning

def send_email(subject: str, body: str):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
    print(f"[email] {subject}")

# ----------------- Main Polling Loop -----------------

async def main_loop():
    state = state_store.load()
    targets = parse_target_dates()

    async with aiohttp.ClientSession(headers={"User-Agent": "SLCTeeTimeFinder/1.0"}) as session:
        while True:
            try:
                for d in targets:
                    for course in COURSE_SOURCES:
                        slots = await check_course(session, course, d)
                        for s in slots:
                            key = f"{course['name']}|{d.isoformat()}|{s['time']}"
                            if state_store.already_sent(state, key):
                                continue
                            subject = f"TEE TIME FOUND: {course['name']} {d.isoformat()}"
                            body = (
                                f"Course:   {course['name']}\n"
                                f"Date:     {d.isoformat()}\n"
                                f"Time:     {s['time']}\n"
                                f"Capacity: {s['capacity'] or 'unknown'}\n"
                                f"URL:      {course['url']}\n"
                            )
                            send_email(subject, body)
                            state_store.mark_sent(state, key)
                            state_store.save(state)

                base = POLL_SECONDS
                jitter = random.randint(-JITTER_SECONDS, JITTER_SECONDS)
                wait = max(60, base + jitter)
                print(f"[loop] Sleeping {wait}s …")
                await asyncio.sleep(wait)

            except Exception as e:
                print("[loop] Error:", e)
                traceback.print_exc()
                await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main_loop())
