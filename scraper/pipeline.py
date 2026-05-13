"""High-level pipeline: scrape → match → enrich → store."""

import logging
from datetime import datetime, timedelta
import os

from scraper.clubexpress import ClubExpressScraper
from scraper.matcher import RouteMatcher
from scraper.rwgps_client import RWGPSClient
from scraper.db import get_session, Ride, RouteCache

log = logging.getLogger(__name__)


def run_pipeline() -> None:
    lookback = int(os.getenv("CE_LOOKBACK_DAYS", "7"))
    since = datetime.now() - timedelta(days=lookback)

    log.info("Pipeline start — scraping rides since %s", since.date())

    with ClubExpressScraper() as scraper:
        raw_rides = scraper.fetch_rides(since=since)

    log.info("Found %d rides", len(raw_rides))

    matcher = RouteMatcher()
    rwgps = RWGPSClient()

    with get_session() as session:
        for raw in raw_rides:
            # Upsert ride record
            ride = session.get(Ride, raw["id"]) or Ride(external_id=raw["id"])
            ride.title = raw["title"]
            ride.ride_date = raw["date"]
            ride.leader = raw.get("leader", "")
            ride.distance_km = raw.get("distance_km")
            ride.description = raw.get("description", "")
            session.add(ride)

            # Skip if already resolved and cached
            cached = session.get(RouteCache, ride.external_id)
            if cached:
                log.debug("Route already cached for ride %s", ride.external_id)
                continue

            # Match → fetch → cache
            route_name = matcher.extract_route_name(raw["description"])
            if not route_name:
                log.warning("No route name found in ride %s: %s", ride.external_id, raw["title"])
                continue

            route_id, geojson = rwgps.resolve_route(route_name)
            if not geojson:
                log.warning("No RWGPS route matched '%s'", route_name)
                continue

            cache_entry = RouteCache(
                ride_external_id=ride.external_id,
                rwgps_route_id=route_id,
                geojson=geojson,
            )
            session.add(cache_entry)
            log.info("Cached route '%s' (RWGPS id=%s) for ride %s", route_name, route_id, ride.external_id)

        session.commit()

    log.info("Pipeline complete")
