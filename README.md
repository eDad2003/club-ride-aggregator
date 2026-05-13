# Club Ride Aggregator

Scrapes a week's worth of club rides from ClubExpress, resolves each ride's
route in RideWithGPS, and renders them all on a single interactive map.

## Stack

| Layer | Technology |
|---|---|
| Scraper | Python · Playwright · BeautifulSoup4 |
| Route matching | RapidFuzz · regex |
| API client | httpx · RideWithGPS REST API |
| Storage | SQLite (Docker volume) |
| Web API | Flask |
| Map UI | Leaflet.js · plain HTML/CSS |
| Orchestration | Docker Compose |

## Quick start

```bash
cp .env.example .env          # fill in your credentials
make dev                      # build + start all services
open http://localhost:5000     # view the map
```

## Development

```bash
make scrape                   # run the scraper once manually
make shell-scraper            # bash into the scraper container
make shell-api                # bash into the api container
make logs                     # tail all container logs
make export-geojson           # dump aggregated GeoJSON to ./output/
```

## Project layout

```
club-ride-aggregator/
├── scraper/          # ClubExpress scraper + route matcher
├── api/              # Flask REST API
├── frontend/         # Static HTML + Leaflet map
├── docker/           # Dockerfiles
├── scripts/          # Helper shell scripts
└── .github/          # CI workflow
```

## Environment variables

See `.env.example` for all required variables.
