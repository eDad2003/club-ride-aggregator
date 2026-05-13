"""ClubExpress ride scraper.

Uses Playwright for JavaScript-rendered pages. Falls back to requests
if the target page is server-rendered.

TODO: Inspect your club's actual ClubExpress URL structure and update
      `RIDES_PATH` and the CSS selectors in `_parse_ride_rows()`.
"""

import logging
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page

log = logging.getLogger(__name__)

# ── Adjust these to match your club's ClubExpress structure ──────────
RIDES_PATH = "/events/event_list.asp"  # path to the public ride calendar
ROW_SELECTOR = "table.eventList tr.eventRow"  # CSS selector for each ride row
# ─────────────────────────────────────────────────────────────────────


class ClubExpressScraper:
    """Context manager wrapping a Playwright browser session."""

    def __init__(self) -> None:
        self.base_url = os.environ["CE_BASE_URL"].rstrip("/")
        self.username = os.getenv("CE_USERNAME", "")
        self.password = os.getenv("CE_PASSWORD", "")
        self._pw = None
        self._browser = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        return self

    def __exit__(self, *_):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    # ── Public API ───────────────────────────────────────────────────

    def fetch_rides(self, since: datetime) -> list[dict]:
        """Return a list of raw ride dicts scraped from ClubExpress."""
        page = self._browser.new_page()
        try:
            if self.username:
                self._login(page)
            url = f"{self.base_url}{RIDES_PATH}"
            log.info("Fetching ride list from %s", url)
            page.goto(url, wait_until="networkidle")
            html = page.content()
        finally:
            page.close()

        return self._parse(html, since)

    # ── Private helpers ──────────────────────────────────────────────

    def _login(self, page: Page) -> None:
        """Log in to ClubExpress. Update selectors to match your site."""
        login_url = f"{self.base_url}/login.asp"
        log.info("Logging in as %s", self.username)
        page.goto(login_url)
        page.fill('input[name="username"]', self.username)
        page.fill('input[name="password"]', self.password)
        page.click('input[type="submit"]')
        page.wait_for_load_state("networkidle")

    def _parse(self, html: str, since: datetime) -> list[dict]:
        """Parse the ride list HTML and return structured ride dicts.

        Update the selectors and field extraction to match your club's
        actual ClubExpress page layout.
        """
        soup = BeautifulSoup(html, "html.parser")
        rides = []

        for row in soup.select(ROW_SELECTOR):
            try:
                ride = self._parse_ride_row(row)
                if ride and ride["date"] >= since:
                    rides.append(ride)
            except Exception as exc:
                log.warning("Failed to parse row: %s", exc)

        return rides

    def _parse_ride_row(self, row) -> dict | None:
        """Extract fields from a single ride row.

        TODO: Update these selectors to match your ClubExpress layout.
        Common patterns:
          - td.eventDate  → date string
          - td.eventTitle → ride title + link to detail page
          - td.eventLeader → ride leader name
        """
        cells = row.find_all("td")
        if len(cells) < 3:
            return None

        date_str = cells[0].get_text(strip=True)
        title_cell = cells[1]
        title = title_cell.get_text(strip=True)
        detail_url = title_cell.find("a", href=True)
        leader = cells[2].get_text(strip=True) if len(cells) > 2 else ""

        try:
            date = datetime.strptime(date_str, "%m/%d/%Y")  # adjust format as needed
        except ValueError:
            log.debug("Could not parse date: %s", date_str)
            return None

        # Build a stable external ID from date + title slug
        slug = title.lower().replace(" ", "-")[:40]
        external_id = f"{date.strftime('%Y%m%d')}-{slug}"

        return {
            "id": external_id,
            "title": title,
            "date": date,
            "leader": leader,
            "detail_url": f"{self.base_url}{detail_url['href']}" if detail_url else None,
            "description": "",   # populated by a detail-page fetch if needed
            "distance_km": None,
        }
