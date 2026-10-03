"""LLM research notes (thesis / bull / bear / risks / contradictions) per symbol, from a
llama.cpp server on the Jetson (OpenAI-compatible API). Inference only: all data
processing stays on this machine.

Usage:
    python -m ai.research AAPL MSFT
    python -m ai.research --top 10            # top 10 by latest total score
"""
import argparse
import json
import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from collector.store import list_symbols, read_news, read_symbol, upsert_symbol
from collector.universe import read_universe
from quant.scoring import CATEGORIES

load_dotenv()

LLM_URL = os.environ.get("LLM_BASE_URL", "http://10.0.0.20:8080")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen")
PROMPT = (Path(__file__).parent / "prompts" / "research.md").read_text()
NOTE_FIELDS = ["thesis", "bull_case", "bear_case", "risks", "contradictions"]
DELTA_MONTHS = 3


def _lines(series: pd.Series, fmt: str = "{:.3f}") -> str:
    return "\n".join(f"- {k}: {fmt.format(v)}" for k, v in series.items() if pd.notna(v)) or "- not in the data"


def build_prompt(symbol: str) -> str:
    scores = read_symbol("scores", symbol).sort_values("as_of")
    metrics = read_symbol("metrics", symbol).sort_values("as_of").iloc[-1]
    financials = read_symbol("financials", symbol)
    annual = financials[financials["period_type"] == "FY"].sort_values(["period", "filed"]).groupby("period").last().iloc[-1]
    news = read_news(symbol).sort_values("published_at").tail(10)
    info = read_universe().set_index("symbol").loc[symbol]

    latest, earlier = scores.iloc[-1], scores.iloc[-1 - DELTA_MONTHS]
    categories = list(CATEGORIES) + ["total"]
    score_lines = "\n".join(
        f"- {c}: {latest[c]:.0f} ({latest[c] - earlier[c]:+.0f})" for c in categories if pd.notna(latest[c]) and pd.notna(earlier[c])
    )
    return PROMPT.format(
        symbol=symbol, name=info["name"], sector=info["sector"], as_of=latest["as_of"].date(), delta_months=DELTA_MONTHS,
        scores=score_lines or "- not in the data",
        factors=_lines(metrics.drop(["symbol", "as_of"])),
        filed=annual["filed"].date(),
        annual=_lines(annual[["revenue", "net_income", "eps", "assets", "liabilities", "cash", "equity", "debt"]], "{:,.2f}"),
        news="\n".join(f"- {r.published_at[:10]} {r.headline}" for r in news.itertuples()) or "- none in the last 30 days",
    )


def ask_llm(prompt: str) -> str:
    resp = requests.post(
        f"{LLM_URL}/v1/chat/completions",
        json={"model": LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
        timeout=600,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def parse_note(text: str) -> dict:
    """The model is asked for JSON but may wrap it in prose or fences; keep the raw text either way."""
    note = dict.fromkeys(NOTE_FIELDS)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            note.update({k: str(parsed[k]) for k in NOTE_FIELDS if k in parsed})
        except json.JSONDecodeError:
            pass
    return {**note, "raw": text}


def top_symbols(n: int) -> list[str]:
    latest = pd.concat([read_symbol("scores", s).tail(1) for s in list_symbols("scores")])
    return latest.nlargest(n, "total")["symbol"].tolist()


def run(symbols: list[str]):
    for symbol in symbols:
        symbol = symbol.upper()
        prompt = build_prompt(symbol)
        try:
            text = ask_llm(prompt)
        except requests.RequestException as exc:
            print(f"[research] {symbol}: LLM unreachable at {LLM_URL}: {exc}")
            return
        scores = read_symbol("scores", symbol)
        row = {"symbol": symbol, "as_of": scores["as_of"].max(), "generated_at": pd.Timestamp.now(), "model": LLM_MODEL, **parse_note(text)}
        path = upsert_symbol("research", symbol, pd.DataFrame([row]), ["as_of"])
        print(f"[research] {symbol} -> {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*")
    parser.add_argument("--top", type=int)
    args = parser.parse_args()
    run(args.symbols or top_symbols(args.top or 10))
