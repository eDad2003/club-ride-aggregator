"""Flask REST API.

Endpoints
---------
GET /                   → serves the Leaflet map UI
GET /api/rides          → JSON list of all rides in the DB
GET /api/map            → GeoJSON FeatureCollection of all cached routes
GET /api/rides/<id>     → single ride + its route feature
"""

import os
import sys

from flask import Flask, jsonify, render_template, abort

# The scraper package is on the same volume; add it to the path
sys.path.insert(0, "/app")

from scraper.db import get_session, Ride, RouteCache

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "../frontend/templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "../frontend/static"),
)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev")


# ── Pages ────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html")


# ── API ──────────────────────────────────────────────────────────────

@app.get("/api/rides")
def list_rides():
    with get_session() as session:
        rides = session.query(Ride).order_by(Ride.ride_date.desc()).all()
        return jsonify([r.to_dict() for r in rides])


@app.get("/api/rides/<ride_id>")
def get_ride(ride_id: str):
    with get_session() as session:
        ride = session.get(Ride, ride_id)
        if not ride:
            abort(404)
        cache = session.get(RouteCache, ride_id)
        return jsonify({
            "ride": ride.to_dict(),
            "route": cache.get_geojson() if cache else None,
        })


@app.get("/api/map")
def aggregated_map():
    """Return a GeoJSON FeatureCollection merging all cached routes.

    Each Feature's properties include the ride metadata so the map UI
    can display a popup without a separate API call.
    """
    with get_session() as session:
        rides = {r.external_id: r for r in session.query(Ride).all()}
        caches = session.query(RouteCache).all()

        features = []
        for cache in caches:
            if not cache.geojson:
                continue
            feature = cache.get_geojson()
            ride = rides.get(cache.ride_external_id)
            if ride:
                feature.setdefault("properties", {})["rwgps_id"] = cache.rwgps_route_id
                feature.setdefault("properties", {}).update(ride.to_dict())
            features.append(feature)

        return jsonify({
            "type": "FeatureCollection",
            "features": features,
        })


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})
