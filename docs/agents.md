# Agent concept

Early design notes for splitting the system into agents. Only the research path exists today
(`ai/research.py`); the rest is a sketch.

| Agent | Responsibility | Status |
|---|---|---|
| Data Analysis | Turn raw filings into structured facts: summarization, entity recognition, relation extraction | Partly: `collector/financials.py` pivots SEC facts, no text extraction yet |
| Investment Research | Event classification, sentiment, market-signal integration | Partly: LLM notes per symbol in `ai/research.py` |
| Investment Manager | Portfolio optimization, risk/return balance | Not built |
| Risk Management | Fraud detection, regulatory compliance | Not built |

A Trading Agent (strategy execution, order decisions) was in the first draft. It is out of scope:
this is a research system and the human makes every decision, so it never places orders.
