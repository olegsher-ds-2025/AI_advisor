"""Daily pipeline: S&P 500 membership -> prices -> SEC facts -> filings -> financials -> factors -> scores -> ML scores -> research notes
-> intraday bars for the watchlist -> static site build (build/site) -> deploy to gh-pages.

Fundamentals are collected upstream on the Jetson (fundamentals/); the financials step
only rebuilds from whatever is there. Steps run in order and the first failure stops the
run, since each step reads the previous one's output.

Usage:
    python -m scheduler.jobs                       # everything
    python -m scheduler.jobs --steps prices factors scoring
    python -m scheduler.jobs --research-top 20 --watchlist-top 50

Cron (weekdays after the US close):
    30 23 * * 1-5  cd /mnt/data/projects/AI_advisor && .venv/bin/python -m scheduler.jobs

On the Jetson it runs weekly as a container, see scheduler/README.md.
"""
import argparse
import logging
import time
from pathlib import Path

from ai import research
from collector import filings, financials, intraday, market, membership, sec_facts
from collector.store import source_symbols
from publish import build, deploy
from quant import factors, model, scoring

log = logging.getLogger("scheduler")
PRICE_PERIOD = "1mo"  # upserts merge by date, so a short window keeps the daily run cheap


def build_steps(research_top: int, watchlist_top: int) -> dict:
    return {
        "membership": membership.run,
        "prices": lambda: market.run(membership.tracked_symbols(), PRICE_PERIOD),
        "sec_facts": lambda: sec_facts.run(membership.tracked_symbols()),
        "filings": lambda: filings.run(source_symbols()),
        "financials": lambda: financials.run(membership.tracked_symbols()),
        "factors": lambda: factors.run([]),
        "scoring": scoring.run,
        "model": model.run,
        "research": lambda: research.run(research.top_symbols(research_top)),
        "intraday": lambda: intraday.run(research.top_symbols(watchlist_top)),
        "site": lambda: build.build(Path("build/site")),
        "deploy": lambda: deploy.deploy(Path("build/site")),
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
