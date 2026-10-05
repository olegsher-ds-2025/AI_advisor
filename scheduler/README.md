# scheduler/

`python -m scheduler.jobs` runs prices -> sec_facts -> financials -> factors -> scoring -> model ->
research -> intraday -> site -> deploy in order and stops at the first failure. Pick steps with `--steps`, notes with
`--research-top N`, intraday watchlist size with `--watchlist-top N`. `site` builds `build/site/`; `deploy` force-pushes it to `gh-pages` (see `publish/deploy.py`). A cron line is in the module docstring; it is not installed.

Fundamentals are collected upstream on the Jetson into `fundamentals/`; the financials step only
rebuilds from whatever is there. `sec_facts` adds the cash-flow, gross profit and operating income facts (~20 min for 495 symbols). A full run takes well over half an hour.
