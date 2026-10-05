# ai/

Inference only, against a llama.cpp server on the Jetson Orin Nano (OpenAI-compatible
`/v1/chat/completions`). Set `LLM_BASE_URL` (default `http://10.0.0.20:8080`) and
`LLM_MODEL` in `.env`.

- `research.py` - per-company context (latest scores and 3-month change, factors, latest
  annual figures, last 30 days of headlines from `news/`) -> thesis / bull case / bear
  case / risks / contradictions, into `advisor/research/`. `python -m ai.research AAPL`
  or `--top 10`. The raw reply is always stored next to the parsed fields.
- `prompts/research.md` - the prompt. It forbids buy/sell advice and outside facts, and
  states that every score is higher-is-better. The current Qwen still misreads scores
  and adds claims now and then, so notes are drafts to check against the numbers.
- `rag.py` - TF-IDF retrieval over one company's filing chunks (`advisor/filings/`, from `python -m collector.filings`: latest 10-K and 10-Q, items 1/1A/7/7A and 2). Used by `assistant/` for ticker questions; research notes do not use it yet. Not built: transcripts, embeddings, a refresh schedule for filings.
