"""Force a full cache refresh for a specific date range.

Usage
-----
docker compose run --rm scraper python scripts/refresh_range.py \
    --since 2026-05-01 --until 2026-05-07

This deletes RouteCache entries for all rides in the given window and
re-scrapes + re-fetches their RWGPS routes from scratch.
"""

import argparse
import logging
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

sys.path.insert(0, "/app")
from scraper.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Full cache refresh for a date range")
    parser.add_argument(
        "--since", required=True,
        help="Start date (inclusive), format: YYYY-MM-DD",
    )
    parser.add_argument(
        "--until", required=True,
        help="End date (inclusive), format: YYYY-MM-DD",
    )
    args = parser.parse_args()

    try:
        since = datetime.strptime(args.since, "%Y-%m-%d")
        until = datetime.strptime(args.until, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )
    except ValueError as e:
        print(f"Error parsing dates: {e}")
        sys.exit(1)

    if since > until:
        print("--since must be before --until")
        sys.exit(1)

    print(f"Full refresh: {since.date()} → {until.date()}")
    run_pipeline(since=since, until=until, full_refresh=True)


if __name__ == "__main__":
    main()
