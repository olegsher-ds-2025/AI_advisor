# scheduler/

`python -m scheduler.jobs` runs prices -> financials -> factors -> scoring -> model ->
research in order and stops at the first failure. Pick steps with `--steps`, notes with
`--research-top N`. A cron line is in the module docstring; it is not installed.

Fundamentals are collected upstream on the Jetson into `fundamentals/`; the financials step only
rebuilds from whatever is there. A full run takes several minutes (factors ~5 min).
