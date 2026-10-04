# scheduler/

`python -m scheduler.jobs` runs prices -> financials -> factors -> scoring -> model ->
research -> intraday -> site in order and stops at the first failure. Pick steps with `--steps`, notes with
`--research-top N`, intraday watchlist size with `--watchlist-top N`. The `site` step only builds `build/site/`. A cron line is in the module docstring; it is not installed.

Fundamentals are collected upstream on the Jetson into `fundamentals/`; the financials step only
rebuilds from whatever is there. A full run takes several minutes (factors ~5 min).
