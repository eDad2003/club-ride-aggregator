# Club Ride Aggregator — Claude Code Context

## What this project does
Scrapes the past week's WCCC club rides from ClubExpress, resolves each
ride's route via RideWithGPS, and renders them all on a single interactive
Leaflet map. The map shows "look what we did" — past rides only, no future.

## Stack

| Layer | Technology |
|---|---|
| Scraper | Python 3.12 · httpx · BeautifulSoup4 |
| Route resolution | Direct RWGPS URL extraction from detail pages |
| Fuzzy fallback | RapidFuzz (for rides without embedded RWGPS links) |
| Storage | SQLite on a Docker named volume (`/data/rides.db`) |
| Web API | Flask 3 |
| Map UI | Plain HTML + Leaflet.js (no build step) |
| Process manager | Supervisord (single combined container) |
| CI/CD | GitHub Actions → ghcr.io → Portainer |

## Project layout
```
club-ride-aggregator/
├── scraper/
│   ├── main.py           # entry point; --once and --full-refresh flags
│   ├── pipeline.py       # orchestrates scrape → enrich → store
│   ├── clubexpress.py    # two-phase scraper (calendar + detail pages)
│   ├── matcher.py        # fuzzy route name fallback (RapidFuzz)
│   ├── rwgps_client.py   # RideWithGPS API client with rate limiting
│   ├── db.py             # SQLAlchemy models: Ride, RouteCache
│   └── tests/
│       └── test_matcher.py
├── api/
│   └── app.py            # Flask; serves UI + /api/rides + /api/map
├── frontend/
│   ├── templates/index.html
│   └── static/
│       ├── css/map.css
│       └── js/map.js     # Leaflet map, sidebar, popups, RideWithGPS links
├── docker/
│   ├── Dockerfile.combined   # single image: supervisord + Flask + scraper
│   ├── supervisord.conf      # runs api (Flask) and scraper (scheduler)
│   ├── Dockerfile.scraper    # legacy, kept for reference
│   └── Dockerfile.api        # legacy, kept for reference
├── scripts/
│   ├── debug_calendar.py     # prints all events in the lookback window
│   └── refresh_range.py      # full cache refresh for a date range
├── docker-compose.yml            # local dev (combined image, port 5003)
├── docker-compose.portainer.yml  # Portainer production stack
├── Makefile
└── .github/workflows/ci.yml      # lint → test → build → push to ghcr.io
```

## Environment variables
Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `CE_BASE_URL` | Yes | `https://wcccpa.clubexpress.com` |
| `RWGPS_API_KEY` | Yes | RideWithGPS API key |
| `FLASK_SECRET_KEY` | Yes | Any random string |
| `CE_LOOKBACK_DAYS` | No | Days of history to scrape (default 7) |
| `SCRAPE_SCHEDULE` | No | Cron expression (default `0 14 * * sun`, Sunday 2pm ET) |
| `RWGPS_USER_ID` | No | Scope RWGPS searches to your club |
| `DATABASE_URL` | No | SQLite path (default `sqlite:////data/rides.db`) |

## Port
The app runs on **port 5003** in all environments.

## Common commands (PowerShell)

```powershell
# Local dev
docker compose up --build
docker compose run --rm app python -m scraper.main --once
docker compose run --rm app python -m scraper.main --once --full-refresh

# Debug — list all events in the lookback window
docker compose run --rm app python scripts/debug_calendar.py

# Force refresh a specific date range
docker compose run --rm app python scripts/refresh_range.py --since 2026-05-01 --until 2026-05-07

# Production equivalents (scripts/ is baked into the image)
docker exec $(docker ps -q --filter name=club-rides) python scripts/debug_calendar.py
docker exec $(docker ps -q --filter name=club-rides) python scripts/refresh_range.py --since 2026-05-01 --until 2026-05-07

# Export aggregated GeoJSON
curl http://localhost:5003/api/map > output/rides.geojson
```

## Scraper architecture (two-phase)

### Phase 1 — Calendar
- Fetches ClubExpress MonthGrid pages for every month in the lookback window
- Handles month boundaries correctly (e.g. scrape window spans May→June)
- Filters out: cancelled rides, future rides, events outside the window
- ClubExpress URLs: page_id=4001 (calendar), page_id=4091 (event detail)

#### Cross-month navigation (important)
ClubExpress tracks the displayed calendar month in **server-side session state**.
The AJAX MonthGrid endpoint (`action=cira&vm=MonthGrid`) always returns the
current session month — passing `_calAction` as a GET parameter is silently
ignored. Navigation to a non-current month requires three steps:

1. GET `content.aspx?page_id=4001&club_id=939827` — full page, harvests VIEWSTATE
2. POST to the same URL with `__EVENTTARGET=ctl00$ctl00$calendar` and
   `__EVENTARGUMENT=V{N}` where N = `(date(year, month, 1) - date(2000, 1, 1)).days`
   (e.g. May 1 2026 → V9617). This sets the server session month.
3. GET the MonthGrid AJAX endpoint — now returns the target month's data.

### Phase 2 — Detail pages
- Fetches each ride's detail page (`page_id=4091&item_id=XXXXX`)
- Searches for RideWithGPS URL in two forms:
  1. Hyperlink: `<a href="https://ridewithgps.com/routes/XXXXXXX">`
  2. Iframe embed: `<iframe src="https://ridewithgps.com/embeds?...&id=XXXXXXX">`
- Rides without a RWGPS link are stored but not cached (retried next scrape)

### Full refresh
- `--full-refresh` flag deletes RouteCache entries for rides in scope
- Ride records are always upserted (title/description may have changed)
- Use `scripts/refresh_range.py` to target a specific date range

## Database schema

**rides** table:
`external_id` (PK, format: `wccc-{item_id}`), `title`, `ride_date`,
`pace` (e.g. "B+", "A-"), `distance_mi` (from RWGPS metadata), `description`, `rwgps_url`, `scraped_at`

**route_cache** table:
`ride_external_id` (PK, FK → rides), `rwgps_route_id`, `geojson` (JSON string), `cached_at`

## API endpoints
- `GET /` — serves the Leaflet map UI
- `GET /api/rides` — JSON list of all rides (most recent first)
- `GET /api/map` — GeoJSON FeatureCollection of all cached routes
- `GET /api/rides/<id>` — single ride + its route GeoJSON
- `GET /api/health` — `{"status": "ok"}`

## Map UI features
- Sidebar: "WCCC Club Rides" title + active date range subtitle
- Date range selector: 1 Week / 1 Month / Custom — client-side filtering, no reload
- Each route is a coloured polyline (red excluded from palette)
- Selecting a route: turns red, brought to front, sidebar highlights
- Popup: ride title, date, distance (mi), pace, "View on RideWithGPS ↗" link
- Rides without a cached route shown at reduced opacity, not clickable
- Auto-zooms to fit all routes on load

## Deployment (Portainer)

CI builds and pushes `ghcr.io/edad2003/club-ride-aggregator:latest` on
every push to `main`. The package must be set to **public** in GitHub:
`github.com/eDad2003 → Packages → club-ride-aggregator → Package settings → Change visibility → Public`

Portainer setup:
1. Stacks → Add Stack → Repository
2. URL: `https://github.com/eDad2003/club-ride-aggregator`
3. Compose path: `docker-compose.portainer.yml`
4. Set env vars: `CE_BASE_URL`, `RWGPS_API_KEY`, `FLASK_SECRET_KEY`
5. Deploy → available on port 5003

## Known limitations / future work
- Rides posted without a RWGPS link won't appear on the map until the
  leader adds one and the scraper runs again
- Member-only rides (those that 302-redirect to the login wall) cannot have
  their detail pages scraped; they will be grayed out on the map
- The fuzzy matcher (RapidFuzz) is a fallback but rarely used since most
  WCCC rides embed the RWGPS URL directly on the detail page
- The scheduler runs in America/New_York timezone (APScheduler + pytz);
  `SCRAPE_SCHEDULE` uses APScheduler cron syntax where `sun` = Sunday
