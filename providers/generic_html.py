import re
from typing import List, Dict
from bs4 import BeautifulSoup

def parse_generic_html(html: str) -> List[Dict]:
    # Very simple parser: extract recognizable times like 7:24 AM, 11:58 AM, etc.
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    time_re = re.compile(r"\b(?:[1-9]|1[0-2]):[0-5]\d\s?(?:AM|PM)\b", re.I)
    results = []
    for m in time_re.finditer(text):
        t = m.group(0).upper().replace(" ", "")
        results.append({"time_str": t, "capacity": None})
    # Deduplicate
    seen = set()
    out = []
    for r in results:
        if r["time_str"] not in seen:
            seen.add(r["time_str"])
            out.append(r)
    return out
