.PHONY: dev build scrape logs shell-scraper shell-api export-geojson lint test clean

# ── Docker Compose shortcuts ────────────────────────────────
dev:
	docker compose up --build

build:
	docker compose build

down:
	docker compose down

logs:
	docker compose logs -f

# ── One-off scrape ──────────────────────────────────────────
scrape:
	docker compose run --rm scraper python -m scraper.main --once

# ── Interactive shells ──────────────────────────────────────
shell-scraper:
	docker compose run --rm scraper bash

shell-api:
	docker compose run --rm api bash

# ── Export ──────────────────────────────────────────────────
export-geojson:
	mkdir -p output
	curl -s http://localhost:5000/api/map | python -m json.tool > output/rides.geojson
	@echo "Wrote output/rides.geojson"

# ── Dev quality ─────────────────────────────────────────────
lint:
	docker compose run --rm scraper ruff check .
	docker compose run --rm api ruff check .

test:
	docker compose run --rm scraper pytest tests/ -v

# ── Cleanup ──────────────────────────────────────────────────
clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
