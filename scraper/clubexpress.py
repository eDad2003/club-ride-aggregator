"""ClubExpress scraper for West Chester Cycling Club.

Uses plain HTTP — no Playwright needed. The MonthGrid view returns
all events for a month as server-rendered HTML with page_id=4091 links.

Filtering rules:
  - Skip anything WITHOUT a ridewithgps.com URL in the description.
  - Skip anything marked CANCELED or CANCELLED.
"""

import logging
import os
import re
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL      = "https://wcccpa.clubexpress.com"
CALENDAR_PATH = "/content.aspx"
CLUB_ID       = "939827"
PAGE_ID       = "4001"

RWGPS_URL_RE = re.compile(
    r"https?://ridewithgps\.com/(routes|trips)/(\d+)", re.IGNORECASE
)

DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"(\w+ \d{1,2}, \d{4}),\s+(\d{1,2}:\d{2} [AP]M)",
    re.IGNORECASE,
)

PACE_RE = re.compile(r"\b(Super B|Gravel B[+-]?|A[+-]?|B[+-]?|C[+-]?)\b")


class ClubExpressScraper:

    def __init__(self) -> None:
        self.base_url = os.getenv("CE_BASE_URL", BASE_URL).rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=30,
            headers={"User-Agent": "ClubRideAggregator/1.0"},
            follow_redirects=True,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._client.close()

    def fetch_rides(self, since: datetime) -> list[dict]:
        """Return ride dicts on/after `since` that have a RWGPS link."""
        now = datetime.now()

        # Fetch every month that overlaps the since→now window
        all_events = []
        for offset in self._month_offsets(since, now):
            all_events.extend(self._parse_calendar(self._fetch_month_grid(offset)))

        # Deduplicate by ride id (same event can appear if months overlap)
        seen, unique = set(), []
        for e in all_events:
            if e["id"] not in seen:
                seen.add(e["id"])
                unique.append(e)

        kept, skipped_date, skipped_no_rwgps, skipped_cancelled = [], 0, 0, 0
        for ride in unique:
            if ride["cancelled"]:
                skipped_cancelled += 1
            elif not ride["rwgps_id"]:
                skipped_no_rwgps += 1
            elif ride["date"] < since:
                skipped_date += 1
            else:
                kept.append(ride)

        log.info(
            "Calendar: %d unique events → %d kept, %d cancelled, "
            "%d no RWGPS link, %d outside window",
            len(unique), len(kept), skipped_cancelled,
            skipped_no_rwgps, skipped_date,
        )
        return kept

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _month_offsets(since: datetime, until: datetime) -> list[int]:
        """Return month offsets (relative to current month) needed to
        cover every month that overlaps the since→until date range.

        Examples (today = May 13):
          since=May 6  → [0]          (only May needed)
          since=Apr 30 → [-1, 0]      (April + May)
          since=May 28 → [0, 1]       (May + June, for a lookahead case)
        """
        now = datetime.now()
        offsets = set()
        cursor = since.replace(day=1)
        end    = until.replace(day=1)
        while cursor <= end:
            diff = (cursor.year - now.year) * 12 + (cursor.month - now.month)
            offsets.add(diff)
            if cursor.month == 12:
                cursor = cursor.replace(year=cursor.year + 1, month=1)
            else:
                cursor = cursor.replace(month=cursor.month + 1)
        return sorted(offsets)

    def _fetch_month_grid(self, offset: int = 0) -> str:
        """Fetch the MonthGrid view for the month at `offset` from now.

        offset=0  → current month
        offset=-1 → previous month
        offset=1  → next month
        """
        params: dict = {
            "page_id": PAGE_ID,
            "club_id": CLUB_ID,
            "action":  "cira",
            "vm":      "MonthGrid",
        }

        if offset != 0:
            now   = datetime.now()
            month = now.month + offset
            year  = now.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            first = datetime(year, month, 1)
            # ClubExpress uses V{ordinal} tokens for month navigation
            params["_calAction"] = f"V{first.toordinal()}"

        resp = self._client.get(CALENDAR_PATH, params=params)
        resp.raise_for_status()

        # Work out which month we fetched for the log message
        now   = datetime.now()
        month = now.month + offset
        year  = now.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        log.info(
            "Fetched MonthGrid %d-%02d (%d bytes)",
            year, month, len(resp.content),
        )
        return resp.text

    def _parse_calendar(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        rides = []
        for link in soup.find_all("a", href=re.compile(r"page_id=4091")):
            try:
                ride = self._parse_event_link(link)
                if ride:
                    rides.append(ride)
            except Exception as exc:
                log.warning("Skipping event — parse error: %s", exc)
        return rides

    def _parse_event_link(self, link) -> dict | None:
        href       = link.get("href", "")
        title_attr = link.get("title", "")
        link_text  = link.get_text(strip=True)

        item_match = re.search(r"item_id=(\d+)", href)
        if not item_match:
            return None
        item_id = item_match.group(1)

        combined  = f"{link_text} {title_attr}".upper()
        cancelled = "CANCELED" in combined or "CANCELLED" in combined

        rwgps_match = RWGPS_URL_RE.search(title_attr)
        rwgps_url   = rwgps_match.group(0) if rwgps_match else None
        rwgps_id    = int(rwgps_match.group(2)) if rwgps_match else None

        date_match = DATE_RE.search(title_attr)
        if not date_match:
            return None
        try:
            ride_dt = datetime.strptime(
                f"{date_match.group(1)} {date_match.group(2)}",
                "%B %d, %Y %I:%M %p",
            )
        except ValueError:
            return None

        description = title_attr[date_match.end():].strip()
        description = re.sub(r"^until \d{1,2}:\d{2} [AP]M\s*", "", description).strip()

        pace_match = PACE_RE.search(link_text)
        pace = pace_match.group(0) if pace_match else ""

        return {
            "id":          f"wccc-{item_id}",
            "item_id":     item_id,
            "title":       link_text,
            "date":        ride_dt,
            "pace":        pace,
            "description": description,
            "detail_url":  f"{self.base_url}{href}" if href.startswith("/") else href,
            "rwgps_url":   rwgps_url,
            "rwgps_id":    rwgps_id,
            "distance_km": None,
            "cancelled":   cancelled,
        }


def fetch_week_of_rides(since: datetime | None = None) -> list[dict]:
    if since is None:
        lookback = int(os.getenv("CE_LOOKBACK_DAYS", "7"))
        since = datetime.now() - timedelta(days=lookback)
    with ClubExpressScraper() as scraper:
        return scraper.fetch_rides(since=since)
