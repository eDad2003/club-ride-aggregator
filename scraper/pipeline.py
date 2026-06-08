"""High-level pipeline: scrape → enrich → store.

Parameters
----------
full_refresh : bool
    If True, delete RouteCache entries for all rides in scope before
    processing. Use this when cached routes are suspected to be stale
    or corrupt. Ride records are always upserted regardless.
since / until : datetime
    Date window to scrape. Defaults to the past CE_LOOKBACK_DAYS days.
"""

import json
import logging
from datetime import datetime, timedelta
import os

from scraper.clubexpress import fetch_rides as ce_fetch
from scraper.rwgps_client import RWGPSClient
from scraper.db import get_session, Ride, RouteCache

log = logging.getLogger(__name__)


def run_pipeline(
    since: datetime | None = None,
    until: datetime | None = None,
    full_refresh: bool = False,
) -> None:
    lookback = int(os.getenv("CE_LOOKBACK_DAYS", "7"))
    if since is None:
        since = datetime.now() - timedelta(days=lookback)
    if until is None:
        until = datetime.now()

    log.info(
        "Pipeline start — window %s → %s, full_refresh=%s",
        since.date(), until.date(), full_refresh,
    )

    # Phase 1: scrape calendar + detail pages
    raw_rides = ce_fetch(since=since, until=until)
    log.info("Scraped %d rides in window", len(raw_rides))

    rwgps  = RWGPSClient()

    with get_session() as session:

        # Full refresh: delete RouteCache for all rides in scope
        if full_refresh:
            ride_ids = [r["id"] for r in raw_rides]
            deleted = (
                session.query(RouteCache)
                .filter(RouteCache.ride_external_id.in_(ride_ids))
                .delete(synchronize_session=False)
            )
            log.info("Full refresh: deleted %d cached routes", deleted)

        for raw in raw_rides:
            # Upsert ride record (always — description/title may have changed)
            ride = session.get(Ride, raw["id"]) or Ride(external_id=raw["id"])
            ride.title       = raw["title"]
            ride.ride_date   = raw["date"]
            ride.pace        = raw.get("pace", "")
            ride.distance_mi = raw.get("distance_mi")
            ride.description = raw.get("description", "")
            ride.rwgps_url   = raw.get("rwgps_url") or ""
            session.add(ride)

            # Skip rides with no RWGPS link — will retry on next scrape
            if not raw.get("rwgps_id"):
                log.info("No RWGPS link (yet): %s — ride will be grayed out on map", raw["title"])
                continue

            # Skip if already cached (and not a full refresh)
            cached = session.get(RouteCache, ride.external_id)
            if cached:
                log.info("Already cached: %s", ride.external_id)
                continue

            # Fetch GeoJSON from RWGPS
            rwgps_id = raw["rwgps_id"]
            geojson  = rwgps.fetch_route_by_id(rwgps_id)

            if not geojson:
                log.warning(
                    "Could not fetch RWGPS route %s for: %s", rwgps_id, raw["title"]
                )
                continue

            distance_m = geojson.get("properties", {}).get("distance_m")
            if distance_m:
                ride.distance_mi = round(distance_m / 1609.34, 1)

            cache_entry = RouteCache(
                ride_external_id=ride.external_id,
                rwgps_route_id=rwgps_id,
                geojson=json.dumps(geojson),
            )
            session.add(cache_entry)
            log.info("Cached RWGPS route %s for: %s", rwgps_id, raw["title"])

        session.commit()

    log.info("Pipeline complete")
