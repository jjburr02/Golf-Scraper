import os, asyncio, random, re
from datetime import datetime, timedelta, date
import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import pytz
import smtplib
from email.mime.text import MIMEText

from providers.lightspeed import parse_lightspeed_html
from providers.generic_html import parse_generic_html
from storage import state as state_store

load_dotenv()

TIMEZONE = os.getenv("TIMEZONE", "America/Denver")
TZ = pytz.timezone(TIMEZONE)

POLL_SECONDS = int(os.getenv("POLL_SECONDS", "600"))
JITTER_SECONDS = int(os.getenv("JITTER_SECONDS", "30"))

# Email configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")   # Your Gmail address
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")   # Gmail App Password
EMAIL_TO = "jjburr@bu.edu"
EMAIL_FROM = SMTP_USERNAME

# Courses to monitor
COURSE_SOURCES = [
    {"name": "Bonneville", "provider": "lightspeed_web", "url": "https://slc-golf.com/bonneville/", "party_size": 4},
    {"name": "Forest Dale", "provider": "lightspeed_web", "url": "https://slc-golf.com/forestdale/", "party_size": 4},
    {"name": "Glendale", "provider": "lightspeed_web", "url": "https://slc-golf.com/glendale/", "party_size": 4},
    {"name": "Mountain Dell", "provider": "lightspeed_web", "url": "https://slc-golf.com/mountaindell/", "party_size": 4},
    {"name": "Nibley Park", "provider": "lightspeed_web", "url": "https://slc-golf.com/nibley-park/", "party_size": 4},
    {"name": "Rose Park", "provider": "lightspeed_web", "url": "https://slc-golf.com/rose-park/", "party_size": 4},
    {"name": "Old Mill (SLCo)", "provider": "lightspeed_web", "url": "https://slco.org/parks-recreation/facilities/golf/old-mill/", "party_size": 4},
]

MORNING_CUTOFF = (12, 0)  # 12:00 PM

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
        if not part: continue
        y,m,d = map(int, part.split("-"))
        out.append(date(y,m,d))
    return out

def is_morning(time_str: str) -> bool:
    m = re.match(r"^(\d{1,2}):(\d{2})\s?(AM|PM)$", time_str, re.I)
    if not m:
        return False
    hh = int(m.group(1)); mm = int(m.group(2)); ampm = m.group(3).upper()
    if ampm == "AM":
        return True
    return False

def capacity_ok(cap) -> bool:
    return (cap is None) or (cap >= 4)

async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as r:
            r.raise_for_status()
            return await r.text()
    except:
        return ""

def extract_slots(provider: str, html: str):
    provider = provider.lower()
    if provider == "lightspeed_web":
        items = parse_lightspeed_html(html)
    else:
        items = parse_generic_html(html)
    out = []
    for it in items:
        t = it.get("time_str","").upper().replace(" ", "")
        t = t.replace("AM", " AM").replace("PM", " PM")
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
    print(f"Email sent: {subject}")

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
                            body = f"Course: {course['name']}\nDate: {d.isoformat()}\nTime: {s['time']}\nCapacity: {s['capacity'] or 'unknown'}"
                            send_email(subject, body)
                            state_store.mark_sent(state, key)
                            state_store.save(state)
                base = POLL_SECONDS
                jitter = random.randint(-JITTER_SECONDS, JITTER_SECONDS)
                wait = max(60, base + jitter)
                await asyncio.sleep(wait)
            except Exception as e:
                print(f"Error in loop: {e}")
                await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main_loop())
