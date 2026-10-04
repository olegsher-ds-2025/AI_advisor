"""Daily pipeline: prices -> financials -> factors -> scores -> ML scores -> research notes
-> intraday bars for the watchlist -> static site build (build/site).

Fundamentals are collected upstream on the Jetson (fundamentals/); the financials step
only rebuilds from whatever is there. Steps run in order and the first failure stops the
run, since each step reads the previous one's output.

Usage:
    python -m scheduler.jobs                       # everything
    python -m scheduler.jobs --steps prices factors scoring
    python -m scheduler.jobs --research-top 20 --watchlist-top 50

Cron (weekdays after the US close):
    30 23 * * 1-5  cd /mnt/data/projects/AI_advisor && .venv/bin/python -m scheduler.jobs
"""
import argparse
import logging
import time
from pathlib import Path

from ai import research
from collector import financials, intraday, market
from collector.store import source_symbols
from publish import build
from quant import factors, model, scoring

log = logging.getLogger("scheduler")
PRICE_PERIOD = "1mo"  # upserts merge by date, so a short window keeps the daily run cheap


def build_steps(research_top: int, watchlist_top: int) -> dict:
    return {
        "prices": lambda: market.run(source_symbols(), PRICE_PERIOD),
        "financials": lambda: financials.run(source_symbols()),
        "factors": lambda: factors.run([]),
        "scoring": scoring.run,
        "model": model.run,
        "research": lambda: research.run(research.top_symbols(research_top)),
        "intraday": lambda: intraday.run(research.top_symbols(watchlist_top)),
        "site": lambda: build.build(Path("build/site")),
    }


def run(step_names: list[str] | None, research_top: int, watchlist_top: int):
    steps = build_steps(research_top, watchlist_top)
    for name in step_names or steps:
        started = time.monotonic()
        log.info("step %s: start", name)
        try:
            steps[name]()
        except Exception:
            log.exception("step %s failed, stopping", name)
            raise SystemExit(1)
        log.info("step %s: done in %.0fs", name, time.monotonic() - started)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", nargs="+", choices=list(build_steps(0, 0)))
    parser.add_argument("--research-top", type=int, default=10)
    parser.add_argument("--watchlist-top", type=int, default=50)
    args = parser.parse_args()
    run(args.steps, args.research_top, args.watchlist_top)
