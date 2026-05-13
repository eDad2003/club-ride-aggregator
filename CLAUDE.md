# Club Ride Aggregator — Claude Code Context

## What this project does
Scrapes a week's worth of club rides from ClubExpress, resolves each ride's
route in RideWithGPS, and renders them all on a single interactive Leaflet map.

## Stack
- **Scraper**: Python 3.12, Playwright (headless Chromium), BeautifulSoup4
- **Route matching**: RapidFuzz + regex heuristics
- **API client**: httpx → RideWithGPS REST API
- **Storage**: SQLite on a Docker named volume (`/data/rides.db`)
- **Web API**: Flask 3
- **Map UI**: Plain HTML + Leaflet.js (no build step)
- **Orchestration**: Docker Compose

## Project layout
```
club-ride-aggregator/
├── scraper/
│   ├── main.py          # entry point; APScheduler loop or --once flag
│   ├── pipeline.py      # orchestrates scrape → match → enrich → store
│   ├── clubexpress.py   # Playwright scraper (CSS selectors need tuning)
│   ├── matcher.py       # route name extraction from ride descriptions
│   ├── rwgps_client.py  # RideWithGPS API client with rate limiting
│   ├── db.py            # SQLAlchemy models: Ride, RouteCache
│   └── tests/
│       └── test_matcher.py
├── api/
│   └── app.py           # Flask app; serves UI + /api/rides + /api/map
├── frontend/
│   ├── templates/index.html
│   └── static/
│       ├── css/map.css
│       └── js/map.js    # Leaflet map logic
├── docker/
│   ├── Dockerfile.scraper
│   └── Dockerfile.api
├── docker-compose.yml
├── Makefile
└── .env.example
```

## Environment variables
Copy `.env.example` to `.env` and fill in:
- `CE_BASE_URL` — your club's ClubExpress base URL
- `CE_USERNAME` / `CE_PASSWORD` — login credentials (if required)
- `CE_LOOKBACK_DAYS` — how many days back to scrape (default 7)
- `RWGPS_API_KEY` — RideWithGPS API key
- `RWGPS_USER_ID` — optional, scopes route searches to your club

## Common commands
```bash
make dev            # build + start all containers
make scrape         # run one scrape manually
make test           # run pytest inside the scraper container
make lint           # ruff check both packages
make logs           # tail all container logs
make export-geojson # dump aggregated GeoJSON to ./output/
make clean          # tear down containers + volumes
```

## Key things still needing configuration
1. **`scraper/clubexpress.py`** — update `RIDES_PATH` and `ROW_SELECTOR`
   to match your club's actual ClubExpress page structure. The file has
   clear TODO comments. Inspect the ride calendar page in DevTools first.

2. **`frontend/static/js/map.js`** — update the default map centre
   (`setView([40.0, -75.5], 10)`) to your club's region.

## Data flow
```
ClubExpress (HTML) → clubexpress.py → pipeline.py → Ride (SQLite)
                                           ↓
                               matcher.py extracts route name
                                           ↓
                          rwgps_client.py → RideWithGPS API
                                           ↓
                               RouteCache (GeoJSON in SQLite)
                                           ↓
                         api/app.py /api/map → Leaflet frontend
```

## Database schema
**rides** table: `external_id` (PK), `title`, `ride_date`, `leader`,
`distance_km`, `description`, `scraped_at`

**route_cache** table: `ride_external_id` (PK, FK → rides), `rwgps_route_id`,
`geojson` (TEXT, stored as JSON string), `cached_at`

## Testing
```bash
make test                        # all tests via Docker
pytest scraper/tests/ -v        # locally if deps installed
```
Tests live in `scraper/tests/`. The matcher is fully unit-testable without
any network calls or Docker.

## Architecture decisions
- SQLite was chosen for simplicity; swap `DATABASE_URL` for a Postgres
  connection string to upgrade with no code changes.
- Routes are cached indefinitely — re-scraping the same ride won't re-hit
  the RWGPS API. Clear the `route_cache` table to force a refresh.
- The scraper and API share the same SQLAlchemy models via the shared
  Docker volume. The API container mounts the scraper source so it can
  import `scraper.db` directly.
