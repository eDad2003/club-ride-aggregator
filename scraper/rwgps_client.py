"""RideWithGPS API client.

Docs: https://ridewithgps.com/api

Key endpoints used:
  GET /routes/<id>.json?apikey=<key>   (metadata + track points)
"""

import logging
import os
import time

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://ridewithgps.com"
MAX_RETRIES = 3
RETRY_DELAY = 2.0    # seconds between retries
RATE_LIMIT_DELAY = 0.5  # seconds between requests


class RWGPSClient:
    def __init__(self) -> None:
        self.api_key = os.environ["RWGPS_API_KEY"]
        self._client = httpx.Client(base_url=BASE_URL, timeout=30)
        self._last_request = 0.0

    # ── Public API ───────────────────────────────────────────────────

    def fetch_route_by_id(self, route_id: int) -> dict | None:
        """Fetch a known route by its RWGPS ID and return a GeoJSON Feature."""
        data = self._get(f"/routes/{route_id}.json", params={"apikey": self.api_key})
        if not data:
            return None
        return self._to_geojson(data.get("route", {}))

    def resolve_route(self, route_name: str) -> tuple[int | None, dict | None]:
        """Search by name, return (rwgps_id, geojson) or (None, None).
        Used as a fallback when no direct RWGPS URL was found.
        """
        params = {
            "apikey": self.api_key,
            "keywords": route_name,
            "limit": 5,
        }
        user_id = os.getenv("RWGPS_USER_ID")
        if user_id:
            params["user_id"] = user_id

        data = self._get("/routes/search.json", params=params)
        if not data:
            return None, None

        results = data.get("results", [])
        if not results:
            return None, None

        best = results[0]
        route_id = best["id"]
        geojson = self.fetch_route_by_id(route_id)
        return route_id, geojson

    # ── Private helpers ──────────────────────────────────────────────

    def _to_geojson(self, route: dict) -> dict | None:
        """Convert a RWGPS route object to a GeoJSON Feature."""
        track_points = route.get("track_points", [])
        coordinates = [
            [pt["x"], pt["y"]]   # RWGPS: x = lng, y = lat
            for pt in track_points
            if "x" in pt and "y" in pt
        ]
        if not coordinates:
            log.warning("Route %s has no track points", route.get("id"))
            return None

        return {
            "type": "Feature",
            "properties": {
                "rwgps_id": route.get("id"),
                "name": route.get("name", ""),
                "distance_m": route.get("distance"),
                "elevation_gain_m": route.get("elevation_gain"),
            },
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
        }

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        """Rate-limited GET with retry logic."""
        elapsed = time.time() - self._last_request
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._client.get(path, params=params)
                self._last_request = time.time()

                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    wait = RETRY_DELAY * attempt
                    log.warning("Rate limited — waiting %.1fs", wait)
                    time.sleep(wait)
                else:
                    log.error("RWGPS %s → HTTP %d", path, resp.status_code)
                    return None

            except httpx.RequestError as exc:
                log.warning("Request error (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        return None

    def close(self) -> None:
        self._client.close()
