"""High-level pipeline: scrape → enrich → store."""

import json
import logging
from datetime import datetime, timedelta
import os

from scraper.clubexpress import fetch_week_of_rides
from scraper.matcher import RouteMatcher
from scraper.rwgps_client import RWGPSClient
from scraper.db import get_session, Ride, RouteCache

log = logging.getLogger(__name__)


def run_pipeline() -> None:
    lookback = int(os.getenv("CE_LOOKBACK_DAYS", "7"))
    since = datetime.now() - timedelta(days=lookback)

    log.info("Pipeline start — scraping rides since %s", since.date())

    raw_rides = fetch_week_of_rides(since=since)
    log.info("Processing %d rides with RWGPS links", len(raw_rides))

    matcher = RouteMatcher()
    rwgps = RWGPSClient()

    with get_session() as session:
        for raw in raw_rides:
            # Upsert ride record
            ride = session.get(Ride, raw["id"]) or Ride(external_id=raw["id"])
            ride.title       = raw["title"]
            ride.ride_date   = raw["date"]
            ride.pace        = raw.get("pace", "")
            ride.distance_km = raw.get("distance_km")
            ride.description = raw.get("description", "")
            ride.rwgps_url   = raw.get("rwgps_url", "") or ""
            session.add(ride)

            # Skip if already cached
            cached = session.get(RouteCache, ride.external_id)
            if cached:
                log.debug("Already cached: %s", ride.external_id)
                continue

            # Resolve route
            rwgps_id = raw.get("rwgps_id")

            if rwgps_id:
                geojson = rwgps.fetch_route_by_id(rwgps_id)
            else:
                route_name = matcher.extract_route_name(raw["description"])
                if not route_name:
                    log.warning("No route found for: %s", raw["title"])
                    continue
                rwgps_id, geojson = rwgps.resolve_route(route_name)

            if not geojson:
                log.warning("Could not fetch RWGPS route %s for: %s", rwgps_id, raw["title"])
                continue

            # Store as JSON string, not dict
            cache_entry = RouteCache(
                ride_external_id=ride.external_id,
                rwgps_route_id=rwgps_id,
                geojson=json.dumps(geojson),
            )
            session.add(cache_entry)
            log.info("Cached RWGPS route %s for: %s", rwgps_id, raw["title"])

        session.commit()

    log.info("Pipeline complete")
