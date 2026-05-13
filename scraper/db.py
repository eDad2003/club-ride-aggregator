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

from sqlalchemy import Column, String, Float, DateTime, Text, Integer, create_engine
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
    distance_km = Column(Float, nullable=True)
    description = Column(Text, default="")
    rwgps_url   = Column(String, default="")          # direct URL if found
    scraped_at  = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.external_id,
            "title": self.title,
            "date": self.ride_date.isoformat() if self.ride_date else None,
            "pace": self.pace,
            "distance_km": self.distance_km,
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


def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional database session."""
    init_db()
    with Session(engine) as session:
        yield session


init_db()
