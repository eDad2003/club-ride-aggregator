"""Database models and session management.

Two tables:
  rides        — one row per ClubExpress ride event
  route_cache  — one row per resolved RWGPS route (keyed by ride external_id)
"""

import json
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from sqlalchemy import Column, String, Float, DateTime, Text, Integer, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/rides.db")

engine = create_engine(
    DATABASE_URL, echo=False, connect_args={"check_same_thread": False}
)


class Base(DeclarativeBase):
    pass


class Ride(Base):
    __tablename__ = "rides"

    external_id = Column(String, primary_key=True)   # "wccc-{item_id}"
    title       = Column(String, nullable=False)
    ride_date   = Column(DateTime, nullable=False)
    pace        = Column(String, default="")          # e.g. "B+", "A-"
    distance_mi      = Column(Float, nullable=True)
    elevation_gain_ft = Column(Float, nullable=True)
    description = Column(Text, default="")
    rwgps_url   = Column(String, default="")          # direct URL if found
    scraped_at  = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.external_id,
            "title": self.title,
            "date": self.ride_date.isoformat() if self.ride_date else None,
            "pace": self.pace,
            "distance_mi": self.distance_mi,
            "elevation_gain_ft": self.elevation_gain_ft,
            "description": self.description,
            "rwgps_url": self.rwgps_url,
        }


class RouteCache(Base):
    __tablename__ = "route_cache"

    ride_external_id = Column(String, primary_key=True)
    rwgps_route_id   = Column(Integer, nullable=True)
    geojson          = Column(Text, nullable=True)   # stored as JSON string
    cached_at        = Column(DateTime, default=datetime.utcnow)

    def get_geojson(self) -> dict | None:
        return json.loads(self.geojson) if self.geojson else None

    def set_geojson(self, data: dict) -> None:
        self.geojson = json.dumps(data)


def _migrate_db() -> None:
    """Apply pending schema changes to an existing database."""
    with engine.connect() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(rides)"))]
        if "distance_km" in cols and "distance_mi" not in cols:
            conn.execute(text("ALTER TABLE rides RENAME COLUMN distance_km TO distance_mi"))
            conn.commit()
        if "elevation_gain_ft" not in cols:
            conn.execute(text("ALTER TABLE rides ADD COLUMN elevation_gain_ft REAL"))
            conn.commit()

        # Backfill distance_mi / elevation_gain_ft from already-cached GeoJSON.
        # Runs once per ride that has a cached route but null metric columns.
        rows = conn.execute(text(
            "SELECT r.external_id, rc.geojson "
            "FROM rides r JOIN route_cache rc ON rc.ride_external_id = r.external_id "
            "WHERE rc.geojson IS NOT NULL "
            "  AND (r.distance_mi IS NULL OR r.elevation_gain_ft IS NULL)"
        )).fetchall()
        for ride_id, geojson_str in rows:
            try:
                props = json.loads(geojson_str).get("properties", {})
                dist_m = props.get("distance_m")
                elev_m = props.get("elevation_gain_m")
                if dist_m:
                    conn.execute(text(
                        "UPDATE rides SET distance_mi = :v WHERE external_id = :id"
                    ), {"v": round(dist_m / 1609.34, 1), "id": ride_id})
                if elev_m:
                    conn.execute(text(
                        "UPDATE rides SET elevation_gain_ft = :v WHERE external_id = :id"
                    ), {"v": round(elev_m * 3.28084), "id": ride_id})
            except Exception:
                pass
        if rows:
            conn.commit()


def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(engine)
    _migrate_db()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional database session."""
    init_db()
    with Session(engine) as session:
        yield session


init_db()
