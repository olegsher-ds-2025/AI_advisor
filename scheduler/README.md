# scheduler/

`python -m scheduler.jobs` runs prices -> sec_facts -> financials -> factors -> scoring -> model ->
research -> intraday -> site -> deploy in order and stops at the first failure. Pick steps with `--steps`, notes with
`--research-top N`, intraday watchlist size with `--watchlist-top N`. `site` builds `build/site/`; `deploy` force-pushes it to `gh-pages` (see `publish/deploy.py`). A cron line is in the module docstring; it is not installed.

Fundamentals are collected upstream on the Jetson into `fundamentals/`; the financials step only
rebuilds from whatever is there. `sec_facts` adds the cash-flow, gross profit and operating income facts (~20 min for 495 symbols). A full run takes well over half an hour.

## On the Jetson

Runs weekly as a container so nothing is installed on the host (the Jetson is production). The
image is built on the Jetson from this repo (`scheduler/Dockerfile`); the lake is mounted read-only
except `advisor/`, memory is capped at 2 GB so llama.cpp keeps its RAM, and `LLM_BASE_URL` points at
the local llama.cpp. `deploy` pushes `gh-pages` over SSH with a repo deploy key (`DEPLOY_KEY`, default
`../deploy_key`, i.e. the repo root next to `scheduler/`); note a write deploy key can also push `main`.

```bash
cd ~/projects/sher_advisor_pipeline
docker compose -f scheduler/docker-compose.yml build
docker compose -f scheduler/docker-compose.yml run --rm pipeline --steps site    # a subset
```

Cron on the Jetson (Sundays 02:00; `flock` stops overlapping runs): see the crontab entry in
`MEMORY.md`.
