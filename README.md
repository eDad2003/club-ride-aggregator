# Club Ride Aggregator

Scrapes a week's worth of WCCC club rides from ClubExpress, resolves each
ride's route in RideWithGPS, and renders them all on a single interactive map.

## Stack

| Layer | Technology |
|---|---|
| Scraper | Python · httpx · BeautifulSoup4 |
| Route matching | Direct RWGPS URL extraction |
| API | Flask |
| Storage | SQLite (Docker volume) |
| Map UI | Leaflet.js |
| Process manager | Supervisord (combined container) |
| Registry | GitHub Container Registry (ghcr.io) |

## Quick start (local)

```bash
cp .env.example .env          # fill in your credentials
docker compose up --build     # build + start
open http://localhost:5003
```

## Common commands

```bash
docker compose run --rm app python -m scraper.main --once                                    # one scrape
docker compose run --rm app python -m scraper.main --once --full-refresh                     # force refresh
docker compose run --rm app python scripts/refresh_range.py --since 2026-05-01 --until 2026-05-07  # backfill range

# Production (scripts/ is baked into the image)
docker exec $(docker ps -q --filter name=club-rides) python scripts/refresh_range.py --since 2026-05-01 --until 2026-05-07
```

## Deployment (Portainer)

The CI pipeline builds and pushes `ghcr.io/edad2003/club-ride-aggregator:latest`
on every push to `main`.

In Portainer:
1. Stacks → Add Stack → Repository
2. Repository URL: `https://github.com/eDad2003/club-ride-aggregator`
3. Compose path: `docker-compose.portainer.yml`
4. Set environment variables (see below)
5. Deploy

### Required environment variables

| Variable | Description |
|---|---|
| `CE_BASE_URL` | `https://wcccpa.clubexpress.com` |
| `RWGPS_API_KEY` | Your RideWithGPS API key |
| `FLASK_SECRET_KEY` | Any random string |

### Optional environment variables

| Variable | Default | Description |
|---|---|---|
| `CE_LOOKBACK_DAYS` | `7` | Days of history to scrape |
| `SCRAPE_SCHEDULE` | `0 14 * * sun` | Cron schedule (default: Sunday 2pm ET) |
| `RWGPS_USER_ID` | — | Scope RWGPS searches to your club |

## Port

The app runs on **port 5003** in all environments.
