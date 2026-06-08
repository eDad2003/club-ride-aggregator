"""ClubExpress scraper for West Chester Cycling Club.

Two-phase scrape:
  1. Fetch MonthGrid calendar pages to get rides in the since→until window
  2. Fetch each ride's detail page to find the RideWithGPS URL (hyperlink or iframe)

Filtering rules:
  - Window is since→until (past only, no future rides)
  - Skip rides marked CANCELED or CANCELLED
  - Rides without a RWGPS URL are returned with rwgps_id=None (pipeline will
    skip them but retry on next scrape, since the route may be added later)
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

# Matches ridewithgps.com/routes/XXXXXXX or /trips/XXXXXXX in any context
RWGPS_RE = re.compile(
    r"https?://ridewithgps\.com/(?:routes|trips)/(\d+)", re.IGNORECASE
)

# Matches the embed iframe: ridewithgps.com/embeds?type=route&id=XXXXXXX
RWGPS_EMBED_RE = re.compile(
    r"https?://ridewithgps\.com/embeds\?[^\"']*?(?:&|)id=(\d+)", re.IGNORECASE
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

    # ── Public API ───────────────────────────────────────────────────

    def fetch_rides(self, since: datetime, until: datetime) -> list[dict]:
        """Return ride dicts for rides in since→until (inclusive).

        Each ride dict always has rwgps_id set (int) or None.
        Cancelled rides are excluded. Rides without a RWGPS URL are
        included with rwgps_id=None so the pipeline can track them
        and retry on the next scrape.
        """
        # Phase 1: collect all calendar events in the window
        candidates = self._collect_calendar_events(since, until)
        log.info("Phase 1: %d non-cancelled rides in window", len(candidates))

        # Phase 2: fetch detail page for each to find RWGPS URL
        rides = []
        for ride in candidates:
            rwgps_id = self._fetch_detail_rwgps_id(ride["detail_url"])
            ride["rwgps_id"] = rwgps_id
            if rwgps_id:
                ride["rwgps_url"] = f"https://ridewithgps.com/routes/{rwgps_id}"
            rides.append(ride)
            status = f"RWGPS={rwgps_id} ({ride['rwgps_url']})" if rwgps_id else "no RWGPS link"
            log.info("%s — %s", ride["title"][:60], status)

        with_route    = sum(1 for r in rides if r["rwgps_id"])
        without_route = len(rides) - with_route
        log.info(
            "Phase 2: %d rides with RWGPS route, %d without",
            with_route, without_route,
        )
        return rides

    # ── Phase 1: calendar ────────────────────────────────────────────

    def _collect_calendar_events(self, since: datetime, until: datetime) -> list[dict]:
        """Fetch MonthGrid pages and return non-cancelled rides in window."""
        all_events = []
        for offset in self._month_offsets(since, until):
            html = self._fetch_month_grid(offset)
            all_events.extend(self._parse_calendar(html, since, until))

        # Deduplicate by ride id
        seen, unique = set(), []
        for e in all_events:
            if e["id"] not in seen:
                seen.add(e["id"])
                unique.append(e)
        return unique

    def _fetch_month_grid(self, offset: int = 0) -> str:
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
            params["_calAction"] = f"V{first.toordinal()}"

        resp = self._client.get(CALENDAR_PATH, params=params)
        resp.raise_for_status()

        now   = datetime.now()
        month = now.month + offset
        year  = now.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        log.info("Fetched MonthGrid %d-%02d (%d bytes)", year, month, len(resp.content))
        return resp.text

    def _parse_calendar(self, html: str, since: datetime, until: datetime) -> list[dict]:
        soup  = BeautifulSoup(html, "html.parser")
        rides = []
        for link in soup.find_all("a", href=re.compile(r"page_id=4091")):
            try:
                ride = self._parse_event_link(link)
                if not ride:
                    continue
                if ride["cancelled"]:
                    log.info("Skipping cancelled: %s", ride["title"])
                    continue
                if ride["date"] < since or ride["date"] > until:
                    continue
                rides.append(ride)
            except Exception as exc:
                log.warning("Skipping event — parse error: %s", exc)
        return rides

    def _parse_event_link(self, link) -> dict | None:
        href      = link.get("href", "")
        title_attr = link.get("title", "")
        link_text  = link.get_text(strip=True)

        item_match = re.search(r"item_id=(\d+)", href)
        if not item_match:
            return None
        item_id = item_match.group(1)

        combined  = f"{link_text} {title_attr}".upper()
        cancelled = "CANCELED" in combined or "CANCELLED" in combined

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

        detail_url = (
            f"{self.base_url}{href}" if href.startswith("/") else href
        )

        return {
            "id":          f"wccc-{item_id}",
            "item_id":     item_id,
            "title":       link_text,
            "date":        ride_dt,
            "pace":        pace,
            "description": description,
            "detail_url":  detail_url,
            "rwgps_url":   None,
            "rwgps_id":    None,
            "distance_mi": None,
            "cancelled":   cancelled,
        }

    # ── Phase 2: detail page ─────────────────────────────────────────

    def _fetch_detail_rwgps_id(self, detail_url: str) -> int | None:
        """Fetch the ride detail page and return the RWGPS route ID, or None."""
        try:
            resp = self._client.get(detail_url, follow_redirects=False)
            if resp.is_redirect:
                location = resp.headers.get("location", "?")
                log.warning(
                    "Detail page redirected — likely member-only content: %s → %s",
                    detail_url, location,
                )
                return None
            resp.raise_for_status()
        except Exception as exc:
            log.warning("Could not fetch detail page %s: %s", detail_url, exc)
            return None

        html = resp.text

        # 1. Check for iframe embed: ridewithgps.com/embeds?...&id=XXXXXXX
        m = RWGPS_EMBED_RE.search(html)
        if m:
            return int(m.group(1))

        # 2. Check for any hyperlink to ridewithgps.com/routes/ or /trips/
        m = RWGPS_RE.search(html)
        if m:
            return int(m.group(1))

        return None

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _month_offsets(since: datetime, until: datetime) -> list[int]:
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


def fetch_rides(
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
    """Convenience function used by the pipeline."""
    if since is None:
        lookback = int(os.getenv("CE_LOOKBACK_DAYS", "7"))
        since = datetime.now() - timedelta(days=lookback)
    if until is None:
        until = datetime.now()
    with ClubExpressScraper() as scraper:
        return scraper.fetch_rides(since=since, until=until)
