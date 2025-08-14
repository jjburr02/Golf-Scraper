# ==== MUST BE THE FIRST LINES OF main.py ====
import os, sys

# Ensure sibling packages (providers/, storage/) are importable
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv()  # used for local dev; Render injects envs via dashboard

# ---- DIAGNOSTIC + REQUIRED ENV ----
def _require_env(name: str) -> str:
    val = os.getenv(name)
    if val is None or (isinstance(val, str) and val.strip() == ""):
        raise RuntimeError(f"Missing required env var: {name}")
    return val

print("[startup] cwd:", os.getcwd())
print("[startup] base dir:", BASE_DIR)
try:
    print("[startup] dir contents:", os.listdir(BASE_DIR))
except Exception as e:
    print("[startup] listdir error:", e)

# Show what the process can actually see (password masked)
print("[startup] SMTP_SERVER:", os.getenv("SMTP_SERVER"))
print("[startup] SMTP_PORT:", os.getenv("SMTP_PORT"))
print("[startup] SMTP_USERNAME:", os.getenv("SMTP_USERNAME"))
print("[startup] SMTP_PASSWORD set?:", "yes" if os.getenv("SMTP_PASSWORD") else "no")

# Assign SMTP settings (fail fast if missing)
SMTP_SERVER   = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = _require_env("SMTP_USERNAME")   # full Gmail address
SMTP_PASSWORD = _require_env("SMTP_PASSWORD")   # 16-char Gmail App Password (no spaces)
EMAIL_TO      = "jjburr02@gmail.com"            # destination email (updated)
EMAIL_FROM    = SMTP_USERNAME                   # sender (same as your SMTP username)
# ==============================================

import asyncio, random, re, traceback
from datetime import datetime, timedelta, date
import aiohttp
import pytz
import smtplib
from email.mime.text import MIMEText

from providers.lightspeed import parse_lightspeed_html
from providers.generic_html import parse_generic_html
from storage import state as state_store

# ---- App settings ----
TIMEZONE = os.getenv("TIMEZONE", "America/Denver")
TZ = pytz.timezone(TIMEZONE)

POLL_SECONDS  = int(os.getenv("POLL_SECONDS", "600"))
JITTER_SECONDS = int(os.getenv("JITTER_SECONDS", "30"))

# ---- Courses to monitor ----
COURSE_SOURCES = [
    {"name": "Bonneville",     "provider": "lightspeed_web", "url": "https://www.chronogolf.com/club/bonneville-golf-course",    "party_size": 4},
    {"name": "Forest Dale",    "provider": "lightspeed_web", "url": "https://www.chronogolf.com/club/forest-dale-golf-course",    "party_size": 4},
    {"name": "Glendale",       "provider": "lightspeed_web", "url": "https://www.chronogolf.com/club/glendale-golf-course",      "party_size": 4},
    {"name": "Mountain Dell",  "provider": "lightspeed_web", "url": "https://www.chronogolf.com/club/mountain-dell-golf-club",  "party_size": 4},
    {"name": "Valley View",    "provider": "lightspeed_web", "url": "https://foreupsoftware.com/index.php/booking/index/19501#teetimes",   "party_size": 4},
    {"name": "Rose Park",      "provider": "lightspeed_web", "url": "https://www.chronogolf.com/club/rose-park-golf-course",     "party_size": 4},
    {"name": "Old Mill (SLCo)","provider": "lightspeed_web", "url": "https://www.chronogolf.com/club/old-mill-slco", "party_size": 4},
    {"name": "Soldier Hollow","provider": "lightspeed_web", "url": "https://stateparks.utah.gov/golf/soldier-hollow/teetime/", "party_size": 4},
]

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
    m = re.match(r"^(\d{1,2}):(\d{2})\s?(AM|PM)$", time_str, re.I)
    if not m:
        return False
    return m.group(3).upper() == "AM"

def capacity_ok(cap) -> bool:
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
    out = []
    for it in items:
        t = (it.get("time_str", "") or "").upper().replace(" ", "")
        t = t.replace("AM", " AM").replace("PM", " PM")
        if not re.match(r"^\d{1,2}:\d{2}\s(AM|PM)$", t):
            continue
        out.append({"time": t, "capacity": it.get("capacity")})
    return out

async def check_course(session, course: dict, target_date: date):
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

# env_smoke.py
import os

print("---- SMTP ENV SMOKE TEST ----")
print("SMTP_SERVER:", os.getenv("SMTP_SERVER"))
print("SMTP_PORT:", os.getenv("SMTP_PORT"))
print("SMTP_USERNAME:", os.getenv("SMTP_USERNAME"))
print("SMTP_PASSWORD set?:", "yes" if os.getenv("SMTP_PASSWORD") else "no")

# Show all SMTP* vars so we can spot typos
smtp_vars = {k: os.getenv(k) for k in os.environ if k.upper().startswith("SMTP_")}
print("All SMTP* envs seen by the process:", smtp_vars)
print("---- END ----")

def send_test_email():
    send_email(
        "TEE TIME FINDER: service started",
        "This is a startup heartbeat to confirm SMTP delivery."
    )
