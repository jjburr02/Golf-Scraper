# Salt Lake City Tee Time Finder (Cloud + SMS)

Continuously polls public Salt Lake City golf course booking pages for **Saturday/Sunday morning** tee times (**before 12:00 PM**) that can fit **4 players**, and sends **SMS alerts via Twilio**.

## Features
- Continuous polling (async) with jitter to be polite.
- SMS notifications via Twilio.
- Pluggable "providers" (Lightspeed/Chronogolf HTML, generic HTML time scraping fallback).
- Persistent state to avoid duplicate SMS for the same slot.
- Ready for **Render** deployment.

## Quick Start (Local)
1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill values (especially Twilio variables).
3. Run:
   ```bash
   python main.py
   ```

## Cloud Deployment (Render)
1. Create a new **Web Service** on Render and connect this repo/zip.
2. Build command:
   ```bash
   pip install -r requirements.txt
   ```
3. Start command:
   ```bash
   python main.py
   ```
4. Add environment variables in Render Dashboard (see `.env.example` for names).

## Course Configuration
Edit `main.py` → `COURSE_SOURCES` to add/adjust courses. Each entry includes:
- `name`: course name.
- `provider`: `"lightspeed_web"` (Chronogolf/Lightspeed HTML) or `"generic_html"` fallback.
- `url`: the public booking page URL.
- `party_size`: number of players to search for (default 4).

### Pre-filled Examples (adjust if needed)
- Bonneville: https://slc-golf.com/bonneville/
- Forest Dale: https://slc-golf.com/forestdale/
- Glendale: https://slc-golf.com/glendale/
- Mountain Dell: https://slc-golf.com/mountaindell/
- Nibley Park: https://slc-golf.com/nibley-park/
- Rose Park: https://slc-golf.com/rose-park/
- Old Mill (SLCo): https://slco.org/parks-recreation/facilities/golf/old-mill/

> **Tip:** These SLC pages usually link out to the actual booking widget (often Lightspeed/Chronogolf).
> If you know the direct booking URL (the page with the tee sheet), paste that as `url` for better accuracy.

## How It Decides "Available for 4"
- The providers try to detect slot capacity from the booking page markup. If capacity cannot be determined,
  the checker will still alert on morning times, but will mark capacity as "unknown".

## SMS De-duplication
We persist a small JSON file in `storage/state.json`. If the same (course, date, time) is seen again, no duplicate SMS is sent.

## Safety & Politeness
- Default polling interval is 10 minutes with ±30 seconds jitter.
- A per-course timeout/backoff is applied on errors.
- Please respect each site's Terms of Use.

## Disclaimer
Websites can change structure. The generic fallback parser looks for recognizable time patterns and may produce false positives.
For best results, update the `url` to point at the **actual booking/teetimes page**.

