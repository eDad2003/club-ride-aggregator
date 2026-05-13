"""ClubExpress scraper for West Chester Cycling Club.

The public calendar is server-rendered HTML — no Playwright needed.
Each event is an <a> tag whose `title` attribute contains the full
description, including (sometimes) a RideWithGPS URL.

Filtering rules applied here:
  - Skip anything WITHOUT a ridewithgps.com URL in the description.
  - Skip anything marked CANCELED or CANCELLED in the link text.
"""

import logging
import os
import re
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL = "https://wcccpa.clubexpress.com"
CALENDAR_PATH = "/content.aspx"
CLUB_ID = "939827"
PAGE_ID = "4001"

# Matches ridewithgps.com/routes/XXXXXXX or /trips/XXXXXXX
RWGPS_URL_RE = re.compile(
    r"https?://ridewithgps\.com/(routes|trips)/(\d+)", re.IGNORECASE
)

# Parses "Monday, April 06, 2026, 5:35 PM until 7:00 PM" from title attr
DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"(\w+ \d{1,2}, \d{4}),\s+(\d{1,2}:\d{2} [AP]M)",
    re.IGNORECASE,
)

PACE_RE = re.compile(r"\b(Super B|Gravel B[+-]?|A[+-]?|B[+-]?|C[+-]?)\b")


class ClubExpressScraper:
    """Scrapes the WCCC ClubExpress calendar using plain HTTP (no browser needed)."""

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

    # ── Public API ───────────────────────────────────────────────────

    def fetch_rides(self, since: datetime) -> list[dict]:
        """Return structured ride dicts for rides on/after `since` that
        have a RideWithGPS link and are not cancelled."""

        # Fetch the months that overlap the lookback window.
        # We need current month and possibly previous month.
        months_to_fetch = self._months_in_range(since, datetime.now())
        all_events = []
        for view_date in months_to_fetch:
            html = self._fetch_calendar_html(view_date)
            all_events.extend(self._parse_calendar(html))

        # Deduplicate by item_id (same event can appear on two month fetches)
        seen = set()
        unique = []
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

    # ── Private: fetch ───────────────────────────────────────────────

    def _fetch_calendar_html(self, view_date: datetime) -> str:
        """Fetch the calendar for the month containing view_date."""
        # ClubExpress uses vd=M/D/YYYY to set the viewed month
        params = {
            "page_id": PAGE_ID,
            "club_id": CLUB_ID,
            "action": "cira",
            "vd": view_date.strftime("%-m/%-d/%Y") if os.name != "nt"
                  else view_date.strftime("%#m/%#d/%Y"),  # Windows strftime
        }
        resp = self._client.get(CALENDAR_PATH, params=params)
        resp.raise_for_status()
        log.info(
            "Fetched calendar for %s (%d bytes)",
            view_date.strftime("%B %Y"), len(resp.content)
        )
        return resp.text

    @staticmethod
    def _months_in_range(since: datetime, until: datetime) -> list[datetime]:
        """Return one datetime per month between since and until."""
        months = []
        current = since.replace(day=1)
        while current <= until:
            months.append(current)
            # Advance to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        return months

    # ── Private: parse ───────────────────────────────────────────────

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
        href = link.get("href", "")
        title_attr = link.get("title", "")
        link_text = link.get_text(strip=True)

        item_match = re.search(r"item_id=(\d+)", href)
        if not item_match:
            return None
        item_id = item_match.group(1)

        combined = f"{link_text} {title_attr}".upper()
        cancelled = "CANCELED" in combined or "CANCELLED" in combined

        rwgps_match = RWGPS_URL_RE.search(title_attr)
        rwgps_url = rwgps_match.group(0) if rwgps_match else None
        rwgps_id = int(rwgps_match.group(2)) if rwgps_match else None

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
            "id": f"wccc-{item_id}",
            "item_id": item_id,
            "title": link_text,
            "date": ride_dt,
            "pace": pace,
            "description": description,
            "detail_url": f"{self.base_url}{href}" if href.startswith("/") else href,
            "rwgps_url": rwgps_url,
            "rwgps_id": rwgps_id,
            "distance_km": None,
            "cancelled": cancelled,
        }


def fetch_week_of_rides(since: datetime | None = None) -> list[dict]:
    """Convenience function used by the pipeline."""
    if since is None:
        lookback = int(os.getenv("CE_LOOKBACK_DAYS", "7"))
        since = datetime.now() - timedelta(days=lookback)
    with ClubExpressScraper() as scraper:
        return scraper.fetch_rides(since=since)
