"""Picks the data an investor question needs and renders it as text for the LLM.

Retrieval is rule-based on purpose: the Jetson's Qwen2.5-3B has no reliable tool calling, so the
service decides what to look up (tickers named in the question, or a ranking by a score category)
and the model only explains what it is given.
"""
import re
import time
from functools import lru_cache

import pandas as pd

from ai.rag import retrieve
from collector.store import list_symbols, read_symbol
from quant.scoring import CATEGORIES

RANKINGS = [*CATEGORIES, "total", "ml_score"]
DEFAULT_TOP = 10
MAX_SYMBOLS = 3
EXCERPTS_TOTAL = 4  # filing chunks per question, split across the symbols asked about
CACHE_SECONDS = 300
DELTA_MONTHS = 3
STALE_DAYS = 10  # delisted ex-members keep their last score; they must not appear in rankings
TICKER = re.compile(r"\$?\b([A-Z]{1,5}(?:[.-][A-Z])?)\b")
TOP_WORDS = re.compile(r"\b(top|best|highest|cheapest|strongest|leaders?|rank(?:ing)?|shortlist|screen)\b", re.I)
CATEGORY_WORDS = {
    "quality": "quality", "growth": "growth", "value": "value", "cheap": "value", "cheapest": "value",
    "momentum": "momentum", "risk": "risk", "safe": "risk", "safest": "risk", "low-risk": "risk",
    "ml": "ml_score", "model": "ml_score",
}


@lru_cache(maxsize=1)
def _latest_cached(bucket: int) -> pd.DataFrame:
    rows = []
    for symbol in list_symbols("scores"):
        scores = read_symbol("scores", symbol)
        ml = read_symbol("ml_scores", symbol)
        latest = scores.sort_values("as_of").iloc[[-1]]
        if ml is not None:
            latest = latest.merge(ml, on=["symbol", "as_of"], how="left")
        rows.append(latest)
    latest = pd.concat(rows, ignore_index=True)
    return latest[latest["as_of"] >= latest["as_of"].max() - pd.Timedelta(days=STALE_DAYS)]


def latest_scores() -> pd.DataFrame:
    return _latest_cached(int(time.time() // CACHE_SECONDS))


def find_symbols(question: str, known: set[str]) -> list[str]:
    """Tickers written in capitals (or as $TICKER); one-letter ones only with the $ sign."""
    found = []
    for match in TICKER.finditer(question):
        symbol = match.group(1)
        if symbol in known and (len(symbol) > 1 or match.group(0).startswith("$")) and symbol not in found:
            found.append(symbol)
    return found[:MAX_SYMBOLS]


def find_category(question: str) -> str:
    lowered = question.lower()
    for word, category in CATEGORY_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            return category
    return "total"


def _fmt(value, fmt="{:.2f}") -> str:
    return fmt.format(value) if pd.notna(value) else "n/a"


def filing_excerpts(symbol: str, question: str, k: int) -> str:
    found = retrieve(symbol, question, k)
    lines = [f"[{r.form} filed {r.filed.date()}, Item {r.item}] {r.text}" for r in found.itertuples()]
    return "\nFiling excerpts matching the question:\n" + "\n".join(lines) if lines else ""


def symbol_context(symbol: str, question: str = "", excerpts: int = 0) -> str:
    scores = read_symbol("scores", symbol).sort_values("as_of")
    metrics = read_symbol("metrics", symbol).sort_values("as_of").iloc[-1]
    latest = scores.iloc[-1]
    earlier = scores.iloc[-1 - DELTA_MONTHS] if len(scores) > DELTA_MONTHS else None
    score_lines = [
        f"- {c}: {_fmt(latest[c], '{:.0f}')}" + (f" ({latest[c] - earlier[c]:+.0f} vs {DELTA_MONTHS}m ago)" if earlier is not None and pd.notna(latest[c]) and pd.notna(earlier[c]) else "")
        for c in [*CATEGORIES, "total"]
    ]
    factor_lines = [f"- {k}: {_fmt(v, '{:.3f}')}" for k, v in metrics.drop(["symbol", "as_of"]).items() if pd.notna(v)]
    text = f"## {symbol} (scores as of {latest['as_of'].date()})\nScores:\n" + "\n".join(score_lines)
    text += "\nFactors:\n" + ("\n".join(factor_lines) or "- not in the data")
    research = read_symbol("research", symbol)
    if research is not None:
        note = research.sort_values("as_of").iloc[-1]
        parts = [f"{f}: {note[f]}" for f in ("thesis", "bull_case", "bear_case", "risks", "contradictions") if pd.notna(note[f])]
        text += f"\nLLM research note (draft, as of {note['as_of'].date()}):\n" + "\n".join(parts)
    return text + (filing_excerpts(symbol, question, excerpts) if excerpts else "")


def ranking_context(category: str, n: int = DEFAULT_TOP) -> str:
    latest = latest_scores()
    column = category if category in latest and latest[category].notna().any() else "total"
    top = latest.dropna(subset=[column]).nlargest(n, column)
    columns = ["symbol", *CATEGORIES, "total"]
    table = top[columns].round(0).astype({c: "Int64" for c in columns[1:]}).to_string(index=False)
    return f"## Top {n} by {column} (scores as of {latest['as_of'].max().date()})\n{table}"


def build_context(question: str) -> str:
    symbols = find_symbols(question, set(list_symbols("scores")))
    if symbols:
        per_symbol = -(-EXCERPTS_TOTAL // len(symbols))
        return "\n\n".join(symbol_context(s, question, per_symbol) for s in symbols)
    category = find_category(question)
    return ranking_context(category) if TOP_WORDS.search(question) or category != "total" else ranking_context("total")
