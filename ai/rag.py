"""Retrieval over the filing chunks in advisor/filings/ (collector.filings).

Lexical TF-IDF, not embeddings: a question about one company searches only that company's few
hundred chunks, so there is nothing to index and no embedding model to host on the Jetson.
"""
import re

import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from collector.store import read_symbol

DEFAULT_K = 3


def _singular(word: str) -> str:
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def analyze(text: str) -> list[str]:
    """Lowercase words without stop words, with plural endings cut so "tariffs" matches "tariff"."""
    words = (w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in ENGLISH_STOP_WORDS)
    return [_singular(w) for w in words]


def retrieve(symbol: str, query: str, k: int = DEFAULT_K) -> pd.DataFrame:
    """Top-k chunks (form, filed, item, text, score) of the symbol's latest filings for the query;
    empty when nothing shares a term with it or the symbol has no filings."""
    chunks = read_symbol("filings", symbol)
    if chunks is None or chunks.empty:
        return pd.DataFrame(columns=["form", "filed", "item", "text", "score"])
    vectorizer = TfidfVectorizer(analyzer=analyze, sublinear_tf=True)
    matrix = vectorizer.fit_transform(chunks["text"])
    scores = (matrix @ vectorizer.transform([query]).T).toarray().ravel()
    top = chunks.assign(score=scores).nlargest(k, "score")
    return top[top["score"] > 0][["form", "filed", "item", "text", "score"]].reset_index(drop=True)
