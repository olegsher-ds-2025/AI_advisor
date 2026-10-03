"""Streamlit research dashboard over advisor/ parquet: top lists, movers, per-company drill-down.

Usage:
    streamlit run dashboard/app.py
"""
import pandas as pd
import streamlit as st

from collector.store import list_symbols, read_symbol
from collector.universe import read_universe
from quant.scoring import CATEGORIES

DELTA_MONTHS = 3
CATEGORY_COLUMNS = list(CATEGORIES) + ["total"]


@st.cache_data(ttl=600)
def load_scores() -> pd.DataFrame:
    scores = pd.concat([read_symbol("scores", s) for s in list_symbols("scores")], ignore_index=True)
    universe = read_universe()
    equities = universe[universe["quote_type"] == "EQUITY"][["symbol", "name", "sector"]]
    return scores.merge(equities, on="symbol")


def latest_with_change(scores: pd.DataFrame) -> pd.DataFrame:
    dates = sorted(scores["as_of"].unique())
    latest = scores[scores["as_of"] == dates[-1]].set_index("symbol")
    earlier = scores[scores["as_of"] == dates[-1 - DELTA_MONTHS]].set_index("symbol")
    latest["total_change"] = latest["total"] - earlier["total"].reindex(latest.index)
    return latest.reset_index()


def show_lists(latest: pd.DataFrame):
    columns = st.columns(3)
    for column, category in zip(columns, ["quality", "growth", "value"]):
        column.subheader(f"Top {category}")
        column.dataframe(latest.nlargest(15, category)[["symbol", "name", category]].round(0), hide_index=True)

    improved, worsened = st.columns(2)
    improved.subheader(f"Biggest improvers ({DELTA_MONTHS}m, total score)")
    improved.dataframe(latest.nlargest(15, "total_change")[["symbol", "name", "total", "total_change"]].round(0), hide_index=True)
    worsened.subheader(f"Biggest deteriorations ({DELTA_MONTHS}m)")
    worsened.dataframe(latest.nsmallest(15, "total_change")[["symbol", "name", "total", "total_change"]].round(0), hide_index=True)


def show_company(latest: pd.DataFrame):
    symbol = st.selectbox("Company", latest.sort_values("symbol")["symbol"])
    info = latest.set_index("symbol").loc[symbol]
    st.subheader(f"{symbol} - {info['name']} ({info['sector']})")

    st.caption("All scores are 0-100 percentiles vs the universe, higher is better (risk 100 = lowest volatility).")
    st.dataframe(info[CATEGORY_COLUMNS].to_frame("score").round(0).T, hide_index=True)

    prices = read_symbol("prices", symbol)
    st.line_chart(prices.set_index("date")["close"])
    st.line_chart(read_symbol("scores", symbol).set_index("as_of")[CATEGORY_COLUMNS])
    st.dataframe(read_symbol("metrics", symbol).sort_values("as_of").tail(1).drop(columns=["symbol"]).T)

    research = read_symbol("research", symbol)
    if research is None:
        st.info("No research note yet. Run `python -m ai.research " + symbol + "`.")
        return
    note = research.sort_values("generated_at").iloc[-1]
    st.markdown(f"**AI research note** ({note['model']}, {note['generated_at']:%Y-%m-%d}) - generated text, verify against the data above.")
    for field in ["thesis", "bull_case", "bear_case", "risks", "contradictions"]:
        st.markdown(f"**{field.replace('_', ' ').title()}**: {note[field] or note['raw']}")


st.set_page_config(page_title="Sher Stock Advisor", layout="wide")
st.title("Sher Stock Advisor AI")
st.caption("Research scores for sorting a universe, not buy/sell signals.")

latest = latest_with_change(load_scores())
sector = st.sidebar.selectbox("Sector", ["All"] + sorted(latest["sector"].dropna().unique()))
if sector != "All":
    latest = latest[latest["sector"] == sector]

lists_tab, company_tab = st.tabs(["Lists", "Company"])
with lists_tab:
    show_lists(latest)
with company_tab:
    show_company(latest)
