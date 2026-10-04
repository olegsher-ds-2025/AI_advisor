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
TIMEFRAMES = {"daily": None, "weekly": "W"}


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


def indicator_snapshot(prices: pd.DataFrame) -> dict:
    bars = prices.set_index("date").sort_index().rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    snapshot = {}
    for name, rule in TIMEFRAMES.items():
        tf = indicators.resample(bars, rule) if rule else bars
        if len(tf) < 30:
            continue
        trend = indicators.supertrend(tf).iloc[-1]
        lines = indicators.alligator(tf).iloc[-1]
        ordered_up = lines["lips"] > lines["teeth"] > lines["jaw"]
        ordered_down = lines["lips"] < lines["teeth"] < lines["jaw"]
        snapshot[name] = {
            "close": tf["close"].iloc[-1],
            "change_pct": (tf["close"].iloc[-1] / tf["close"].iloc[-2] - 1) * 100,
            "rsi": indicators.rsi(tf["close"]).iloc[-1],
            "atr": indicators.atr(tf).iloc[-1],
            "supertrend": trend["supertrend"],
            "supertrend_direction": int(trend["direction"]),
            "alligator": "up" if ordered_up else "down" if ordered_down else "sleeping",
            "iix": indicators.iix(tf).iloc[-1],
        }
    return snapshot


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
        "indicators": indicator_snapshot(prices),
        "research": research_note(symbol),
    }


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

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC_DIR, out)
    shutil.copy(CNAME, out / "CNAME")
    (out / ".nojekyll").touch()

    rows = index_rows(frames, universe)
    as_of = max(df["as_of"].max() for df in frames.values())
    _dump(out / "data" / "index.json", _rounded({"as_of": as_of, "generated_at": pd.Timestamp.now(tz="UTC"), "delta_months": DELTA_MONTHS, "rows": rows}))
    for symbol in symbols:
        _dump(out / "data" / "symbols" / f"{symbol}.json", _rounded(symbol_payload(symbol, universe.loc[symbol])))
    print(f"[publish] {len(symbols)} symbols, as of {as_of:%Y-%m-%d} -> {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("build/site"))
    build(parser.parse_args().out)
