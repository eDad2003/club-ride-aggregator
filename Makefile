.PHONY: dev build scrape logs shell export-geojson lint test clean

# ── Local dev ───────────────────────────────────────────────────────
dev:
	docker compose up --build

build:
	docker compose build

down:
	docker compose down

logs:
	docker compose logs -f

# ── One-off scrape ──────────────────────────────────────────────────
scrape:
	docker compose run --rm app python -m scraper.main --once

scrape-refresh:
	docker compose run --rm app python -m scraper.main --once --full-refresh

# ── Interactive shell ───────────────────────────────────────────────
shell:
	docker compose run --rm app bash

# ── Export ──────────────────────────────────────────────────────────
export-geojson:
	mkdir -p output
	curl -s http://localhost:5003/api/map | python -m json.tool > output/rides.geojson
	@echo "Wrote output/rides.geojson"

# ── Quality ─────────────────────────────────────────────────────────
lint:
	docker compose run --rm app ruff check scraper/ api/

test:
	docker compose run --rm app pytest scraper/tests/ -v

# ── Cleanup ─────────────────────────────────────────────────────────
clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
