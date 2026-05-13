"""Entry point for the scraper service.

Run modes
---------
python -m scraper.main                        # starts the APScheduler loop
python -m scraper.main --once                 # runs one scrape and exits
python -m scraper.main --once --full-refresh  # one scrape, clears route cache first
"""

import argparse
import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

from scraper.pipeline import run_pipeline

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once", action="store_true",
        help="Run one scrape then exit (default: run on schedule)",
    )
    parser.add_argument(
        "--full-refresh", action="store_true",
        help="Delete cached routes for rides in scope before scraping",
    )
    args = parser.parse_args()

    if args.once:
        log.info("Running single scrape (full_refresh=%s)...", args.full_refresh)
        run_pipeline(full_refresh=args.full_refresh)
        return

    schedule = os.getenv("SCRAPE_SCHEDULE", "0 6 * * 1")
    minute, hour, day, month, day_of_week = schedule.split()

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_pipeline,
        trigger="cron",
        kwargs={"full_refresh": args.full_refresh},
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
    )
    log.info("Scheduler started. Next run: %s", scheduler.get_jobs()[0].next_run_time)
    scheduler.start()


if __name__ == "__main__":
    main()
