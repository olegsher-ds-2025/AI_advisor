# publish/

Static GitHub Pages site generated from the `advisor/` parquet data.

- `python -m publish.build [--out DIR]` writes `build/site/`: `data/index.json`, one
  `data/symbols/<TICKER>.json` per equity, `CNAME`, `.nojekyll` and the front end from `static/`.
- Published: scores, 1y closes, score history, factors, indicator snapshots (1-480 min, daily,
  weekly) and LLM research notes. Not published: financials, facts, news.
- Intraday indicators appear only for symbols collected by `collector.intraday` (the watchlist).
- Serve locally with `python -m http.server -d build/site`.

The parquet lake is only reachable from this machine, so GitHub Actions can't build the site.
The built directory is pushed to the `gh-pages` branch instead.
