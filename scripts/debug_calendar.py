"""Debug script — prints all calendar events in the lookback window.
Run inside the scraper container:
  docker compose run --rm scraper python scripts/debug_calendar.py
"""

import os
import re
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

BASE_URL = os.getenv("CE_BASE_URL", "https://wcccpa.clubexpress.com")
LOOKBACK = int(os.getenv("CE_LOOKBACK_DAYS", "7"))

DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"(\w+ \d{1,2}, \d{4}),\s+(\d{1,2}:\d{2} [AP]M)",
    re.IGNORECASE,
)
RWGPS_RE = re.compile(
    r"https?://ridewithgps\.com/(routes|trips)/(\d+)", re.IGNORECASE
)

client = httpx.Client(
    timeout=30,
    headers={"User-Agent": "ClubRideAggregator/1.0"},
    follow_redirects=True,
)

resp = client.get(
    f"{BASE_URL}/content.aspx",
    params={"page_id": "4001", "club_id": "939827", "action": "cira", "vm": "MonthGrid"},
)
resp.raise_for_status()
print(f"Fetched {len(resp.content)} bytes  (HTTP {resp.status_code})")

soup  = BeautifulSoup(resp.text, "html.parser")
since = datetime.now() - timedelta(days=LOOKBACK)
all_links = soup.find_all("a", href=re.compile(r"page_id=4091"))
print(f"Total page_id=4091 links on page: {len(all_links)}")
print(f"Lookback window: {since.date()} → {datetime.now().date()}\n")

rows = []
for link in all_links:
    ta   = link.get("title", "")
    text = link.get_text(strip=True)
    dm   = DATE_RE.search(ta)
    if not dm:
        continue
    try:
        dt = datetime.strptime(f"{dm.group(1)} {dm.group(2)}", "%B %d, %Y %I:%M %p")
    except ValueError:
        continue

    cancelled = "CANCEL" in (text + ta).upper()
    rwgps     = RWGPS_RE.search(ta)
    rwgps_id  = rwgps.group(2) if rwgps else "-"
    in_window = dt >= since

    rows.append((dt, text[:55], cancelled, rwgps_id, in_window))

rows.sort()

print(f"{'Date':<12} {'In Win':<7} {'Cxl':<5} {'RWGPS ID':<12} Title")
print("-" * 90)
for dt, title, cancelled, rwgps_id, in_window in rows:
    print(
        f"{str(dt.date()):<12} "
        f"{'YES' if in_window else 'no':<7} "
        f"{'Y' if cancelled else 'N':<5} "
        f"{rwgps_id:<12} "
        f"{title}"
    )

in_window_count = sum(1 for r in rows if r[4])
print(f"\nTotal shown: {len(rows)}  |  In window: {in_window_count}")
