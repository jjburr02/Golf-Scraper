import re
from typing import List, Dict
from bs4 import BeautifulSoup

# Heuristic parser for Lightspeed (Chronogolf) public booking pages.
# It looks for time blocks and, when possible, party/capacity hints.
# Returns list of dicts: {time_str, capacity (int|None)}
def parse_lightspeed_html(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Common patterns on Lightspeed booking pages: time elements and availability containers
    # Fallback: regex times like 7:12 AM
    time_re = re.compile(r"\b(?:[1-9]|1[0-2]):[0-5]\d\s?(?:AM|PM)\b", re.I)

    # Try to find obvious "slot" containers first
    for slot in soup.select("[class*='tee'], [class*='time'], [data-testid*='time']") or []:
        text = slot.get_text(" ", strip=True)
        for m in time_re.finditer(text):
            t = m.group(0).upper().replace(" ", "")
            # Capacity hints near the time
            snippet = text[max(0, m.start()-40):m.end()+40]
            cap = None
            # Look for patterns like "4 left", "4 spots", "x4", etc.
            cap_m = re.search(r"(\b[1-4]\b)\s*(left|spots|available)|x\s*([1-4])", snippet, re.I)
            if cap_m:
                cap = int(cap_m.group(1) or cap_m.group(3))
            results.append({"time_str": t, "capacity": cap})

    # If nothing found, run a global regex
    if not results:
        for m in time_re.finditer(soup.get_text(" ", strip=True)):
            t = m.group(0).upper().replace(" ", "")
            results.append({"time_str": t, "capacity": None})

    # De-duplicate
    uniq = {}
    for r in results:
        uniq[r["time_str"]] = r
    return list(uniq.values())
