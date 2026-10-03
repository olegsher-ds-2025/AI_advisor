# ai/ (not yet implemented)

Planned for V1.5-V1.6, runs against Qwen on the Jetson Orin Nano (10.0.0.20) via
llama.cpp, not on this machine:

- `research.py` - builds a per-company context (metrics, score deltas, latest
  filings/earnings/news) and prompts the LLM for thesis / bull case / bear case /
  risks / contradictions. Writes to the `research` table.
- `rag.py` - indexes 10-K/10-Q/8-K/earnings transcripts into pgvector (or Qdrant
  later) for natural-language queries over filings.
- `prompts/` - prompt templates for the above.

Requires the `research` table (not created yet) and a reachable Jetson inference
endpoint.
