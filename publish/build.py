"""Static site for GitHub Pages: advisor/ parquet -> JSON + a small static front end.

Publishes scores, price history, indicator snapshots and LLM research notes only. Raw
financials/facts and news never leave the machine.

Usage:
    python -m publish.build                  # -> build/site
    python -m publish.build --out /tmp/site
"""
import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from collector.intraday import dataset as intraday_dataset
from collector.store import list_symbols, read_symbol
from collector.universe import read_universe
from quant import indicators
from quant.scoring import CATEGORIES

STATIC_DIR = Path(__file__).parent / "static"
CNAME = Path(__file__).parents[1] / "CNAME"
DELTA_MONTHS = 3
PRICE_DAYS = 252
SCORE_COLUMNS = list(CATEGORIES) + ["total"]
NOTE_FIELDS = ["thesis", "bull_case", "bear_case", "risks", "contradictions"]
US_OPEN = "9h30min"
MIN_BARS = 30
# label -> (source dataset or interval, resample rule, offset); label order is the page's column order
INTRADAY_TIMEFRAMES = {
    "1m": ("1m", None), "5m": ("5m", None), "15m": ("15m", None), "30m": ("30m", None), "60m": ("60m", None),
    "120m": ("60m", "120min"), "240m": ("60m", "240min"), "480m": ("60m", "480min"),
}


def _clean(value):
    if isinstance(value, (float, np.floating)):
        return None if np.isnan(value) else round(float(value), 4)
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    if isinstance(value, np.integer):
        return int(value)
    return value


def _dump(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=_clean, separators=(",", ":"), allow_nan=False))


def _rounded(obj):
    if isinstance(obj, dict):
        return {k: _rounded(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rounded(v) for v in obj]
    return _clean(obj)


def snapshot_of(tf: pd.DataFrame) -> dict | None:
    if len(tf) < MIN_BARS:
        return None
    trend = indicators.supertrend(tf).iloc[-1]
    lines = indicators.alligator(tf).iloc[-1]
    ordered_up = lines["lips"] > lines["teeth"] > lines["jaw"]
    ordered_down = lines["lips"] < lines["teeth"] < lines["jaw"]
    return {
        "close": tf["close"].iloc[-1],
        "change_pct": (tf["close"].iloc[-1] / tf["close"].iloc[-2] - 1) * 100,
        "rsi": indicators.rsi(tf["close"]).iloc[-1],
        "atr": indicators.atr(tf).iloc[-1],
        "supertrend": trend["supertrend"],
        "supertrend_direction": int(trend["direction"]),
        "alligator": "up" if ordered_up else "down" if ordered_down else "sleeping",
        "iix": indicators.iix(tf).iloc[-1],
    }


def intraday_bars(symbol: str, interval: str) -> pd.DataFrame | None:
    bars = read_symbol(intraday_dataset(interval), symbol)
    return None if bars is None else bars.set_index("ts").sort_index()[["open", "high", "low", "close", "volume"]]


def indicator_snapshot(symbol: str, prices: pd.DataFrame) -> dict:
    bars = prices.set_index("date").sort_index().rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    frames = {}
    for label, (interval, rule) in INTRADAY_TIMEFRAMES.items():
        source = intraday_bars(symbol, interval)
        if source is not None:
            frames[label] = indicators.resample(source, rule, US_OPEN) if rule else source
    frames["daily"], frames["weekly"] = bars, indicators.resample(bars, "W")
    snapshots = {label: snapshot_of(tf) for label, tf in frames.items()}
    return {label: snap for label, snap in snapshots.items() if snap}


def research_note(symbol: str) -> dict | None:
    research = read_symbol("research", symbol)
    if research is None:
        return None
    note = research.sort_values("generated_at").iloc[-1]
    body = {f: note[f] for f in NOTE_FIELDS}
    if not any(body.values()):
        body["thesis"] = note["raw"]
    return {"generated_at": note["generated_at"], "as_of": note["as_of"], "model": note["model"], **body}


def symbol_payload(symbol: str, info: pd.Series) -> dict:
    scores = read_symbol("scores", symbol).sort_values("as_of")
    prices = read_symbol("prices", symbol).sort_values("date")
    recent = prices.tail(PRICE_DAYS)
    metrics = read_symbol("metrics", symbol).sort_values("as_of").iloc[-1].drop(["symbol", "as_of"])
    return {
        "symbol": symbol,
        "name": info["name"],
        "sector": info["sector"],
        "industry": info["industry"],
        "prices": {"date": recent["date"].dt.strftime("%Y-%m-%d").tolist(), "close": recent["close"].tolist()},
        "score_history": {"as_of": scores["as_of"].dt.strftime("%Y-%m-%d").tolist(), **{c: scores[c].tolist() for c in SCORE_COLUMNS}},
        "factors": metrics.to_dict(),
        "indicators": indicator_snapshot(symbol, prices),
        "research": research_note(symbol),
    }


FACTOR_LABELS = {
    "net_margin": "net margin", "roe": "return on equity", "roa": "return on assets",
    "debt_to_equity": "debt/equity", "liabilities_to_assets": "liabilities/assets",
    "revenue_growth": "revenue growth", "net_income_growth": "net income growth", "eps_growth": "EPS growth",
    "pe": "P/E", "ps": "P/S", "pb": "P/B",
    "ret_3m": "3m return", "ret_6m": "6m return", "ret_12m_ex_1m": "12m return excl. last month", "sma200_gap": "distance above the 200-day average",
    "vol_60d": "60-day volatility", "drawdown_252d": "drawdown from the 1-year high",
}
TOP_N = 10


def column_help() -> dict:
    help_ = {
        category: "Percentile vs the universe (0-100, higher is better) of: "
        + ", ".join(f"{FACTOR_LABELS[f]} ({'higher' if higher else 'lower'} is better)" for f, higher in factors.items())
        + "."
        for category, factors in CATEGORIES.items()
    }
    help_["total"] = "Average of the five category scores."
    help_["total_change"] = "Change in the total score versus three months ago, in score points."
    help_["sector"] = "Sector reported by Yahoo Finance."
    return help_


def top_picks(rows: list[dict], payloads: dict[str, dict]) -> list[dict]:
    complete = [r for r in rows if all(r[c] is not None and not pd.isna(r[c]) for c in SCORE_COLUMNS)]
    picks = []
    for row in sorted(complete, key=lambda r: -r["total"])[:TOP_N]:
        payload = payloads[row["symbol"]]
        daily = payload["indicators"].get("daily", {})
        note = payload["research"]
        picks.append(
            {
                **row,
                "daily": daily,
                "thesis": note["thesis"] if note else None,
            }
        )
    return picks


def index_rows(frames: dict[str, pd.DataFrame], universe: pd.DataFrame) -> list[dict]:
    rows = []
    for symbol, scores in frames.items():
        scores = scores.sort_values("as_of")
        latest, earlier = scores.iloc[-1], scores.iloc[-1 - DELTA_MONTHS] if len(scores) > DELTA_MONTHS else None
        info = universe.loc[symbol]
        rows.append(
            {
                "symbol": symbol,
                "name": info["name"],
                "sector": info["sector"],
                **{c: latest[c] for c in SCORE_COLUMNS},
                "total_change": latest["total"] - earlier["total"] if earlier is not None else None,
            }
        )
    return rows


def build(out: Path):
    universe = read_universe()
    universe = universe[universe["quote_type"] == "EQUITY"].set_index("symbol")
    symbols = [s for s in list_symbols("scores") if s in universe.index]
    frames = {s: read_symbol("scores", s) for s in symbols}
    frames = {s: df for s, df in frames.items() if len(df) > DELTA_MONTHS}
    symbols = list(frames)

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC_DIR, out)
    shutil.copy(CNAME, out / "CNAME")
    (out / ".nojekyll").touch()

    rows = index_rows(frames, universe)
    as_of = max(df["as_of"].max() for df in frames.values())
    payloads = {symbol: symbol_payload(symbol, universe.loc[symbol]) for symbol in symbols}
    for symbol, payload in payloads.items():
        _dump(out / "data" / "symbols" / f"{symbol}.json", _rounded(payload))
    index = {
        "as_of": as_of,
        "generated_at": pd.Timestamp.now(tz="UTC"),
        "delta_months": DELTA_MONTHS,
        "columns": column_help(),
        "top": top_picks(rows, payloads),
        "rows": rows,
    }
    _dump(out / "data" / "index.json", _rounded(index))
    print(f"[publish] {len(symbols)} symbols, as of {as_of:%Y-%m-%d} -> {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("build/site"))
    build(parser.parse_args().out)
