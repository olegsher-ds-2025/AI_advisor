"""CIK + SIC for every symbol Fool picked (incl. delisted ones, found by company name) and for lake control symbols; SEC facts for the delisted picks.

SIC is assigned per company and rarely changes, so it is a better 'sector at the time' than today's yfinance sector.
-> advisor/fool/ciks.parquet (symbol, cik, sec_name, sic, sic_desc, match) and advisor/facts_extra/ (same as collector.sec_facts)."""
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from collector.sec_facts import FACTS_URL, KEYS, USER_AGENT, _get, extract_facts, ticker_to_cik
from collector.store import upsert_symbol
from fool.ingest import FOOL_DIR

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar?"
CIKS_PATH = FOOL_DIR / "ciks.parquet"
GAP = 0.15
# name matching can't tell the original company from a later namesake when no XBRL facts predate the pick (pre-2009)
CIK_OVERRIDES = {"BBBY": 886158, "MFE": 890801, "ZAYO": 1608249}
SUFFIXES = {"inc", "corp", "corporation", "co", "company", "ltd", "limited", "holdings", "holding", "group", "plc", "the", "de", "new", "incorporated", "sa", "nv", "llc", "lp"}


def normalize(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower().replace("&", " and ")).split()
    return " ".join(w for w in words if w not in SUFFIXES)


def retry(fn, *args):
    for wait in (5, 20, 60, 180):
        try:
            return fn(*args)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503):
                raise
            time.sleep(wait)
    return fn(*args)


def candidate_ciks(name: str) -> list[int]:
    url = BROWSE_URL + urllib.parse.urlencode({"company": name, "type": "10-K", "owner": "include", "count": "10", "action": "getcompany", "output": "atom"})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=30) as r:
        text = r.read().decode("latin-1")
    time.sleep(GAP)
    return list(dict.fromkeys(int(c) for c in re.findall(r"<cik>(\d+)</cik>", text)))


def submissions(cik: int) -> dict:
    time.sleep(GAP)
    return _get(SUBMISSIONS_URL.format(cik=cik))


def meta(cik: int, sub: dict) -> dict:
    return {"cik": cik, "sec_name": sub.get("name"), "sic": pd.to_numeric(sub.get("sic"), errors="coerce"), "sic_desc": sub.get("sicDescription")}


def n_facts(cik: int, known_by: pd.Timestamp) -> tuple[int, int]:
    """(facts filed on or before known_by, all facts): the operating company at pick time has the first number large."""
    try:
        facts = extract_facts(retry(_get, FACTS_URL.format(cik=cik)))
    except OSError:
        return 0, 0
    return int((pd.to_datetime(facts["filed_at"]) <= known_by).sum()), len(facts)


def resolve(symbol: str, company: str, live: dict[str, int], known_by: pd.Timestamp) -> dict | None:
    if symbol in CIK_OVERRIDES:
        return {**meta(CIK_OVERRIDES[symbol], retry(submissions, CIK_OVERRIDES[symbol])), "match": "override"}
    if symbol in live:
        return {**meta(live[symbol], submissions(live[symbol])), "match": "ticker"}
    target = normalize(re.sub(r"\(.*?\)", "", company))
    hits = []
    for cik in retry(candidate_ciks, company):
        sub = retry(submissions, cik)
        names = {normalize(sub.get("name", "")), *(normalize(f["name"]) for f in sub.get("formerNames", []))}
        if target and target in names:
            hits.append(meta(cik, sub))
    if not hits:
        return None
    if len(hits) == 1:
        return {**hits[0], "match": "name"}
    # old and new entities can share a name (Bed Bath & Beyond, McAfee...); pick the one that had the most facts filed by the time of the pick
    sizes = [n_facts(h["cik"], known_by) for h in hits]
    return {**hits[sizes.index(max(sizes))], "match": f"name-best-of-{len(hits)}"}


def main(limit: int | None = None) -> None:
    recs = pd.read_parquet(FOOL_DIR / "recs.parquet")
    buys = recs[recs["action"] == "BUY"]
    picked = buys.drop_duplicates("yf_symbol")[["yf_symbol", "company"]]
    last_pick = buys.groupby("yf_symbol")["rec_date"].max()
    live = {k.replace(".", "-"): v for k, v in ticker_to_cik().items()}
    rows, missing = [], []
    for sym, company in picked.head(limit).itertuples(index=False):
        try:
            found = resolve(sym, company, live, last_pick[sym])
        except OSError as e:
            print(f"{sym}: {e}")
            found = None
        (rows if found else missing).append({"symbol": sym, **found} if found else sym)
    out = pd.DataFrame(rows)
    out.to_parquet(CIKS_PATH, index=False)
    print(f"resolved {len(out)}/{len(picked)}: {out['match'].value_counts().to_dict()}; unresolved: {missing}")
    for r in out[out["match"] != "ticker"].itertuples():
        try:
            facts = extract_facts(_get(FACTS_URL.format(cik=r.cik)))
        except OSError as e:
            print(f"{r.symbol}: facts {e}")
            continue
        if not facts.empty:
            upsert_symbol("facts_extra", r.symbol, facts, KEYS)
        time.sleep(GAP)


if __name__ == "__main__":
    main()


LAKE_CIKS_PATH = FOOL_DIR / "ciks_lake.parquet"


def lake_meta(symbols: list[str]) -> pd.DataFrame:
    """CIK + SIC for control symbols (current tickers only); cached."""
    cached = pd.read_parquet(LAKE_CIKS_PATH) if LAKE_CIKS_PATH.exists() else pd.DataFrame(columns=["symbol", "cik", "sec_name", "sic", "sic_desc"])
    todo = [s for s in symbols if s not in set(cached["symbol"])]
    if todo:
        live = {k.replace(".", "-"): v for k, v in ticker_to_cik().items()}
        rows = []
        for s in todo:
            try:
                rows.append({"symbol": s, **meta(live[s], retry(submissions, live[s]))} if s in live else {"symbol": s})
            except OSError as e:
                print(f"{s}: {e}")
        cached = pd.concat([cached, pd.DataFrame(rows)], ignore_index=True)
        cached.to_parquet(LAKE_CIKS_PATH, index=False)
    return cached
