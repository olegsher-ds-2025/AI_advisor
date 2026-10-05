# assistant/

Chat with the advisor's own data from Open WebUI. `app.py` is an OpenAI-compatible endpoint
(`/v1/models`, `/v1/chat/completions` with streaming) that Open WebUI lists as the model `sher-advisor`.

For each question `context.py` decides what to look up and `app.py` puts it in the system prompt
(`prompts/system.md`) before forwarding to the llama.cpp backend (`LLM_BASE_URL`):

- tickers written in capitals (`$A` for one-letter ones) -> that symbol's latest scores with the
  3-month change, factors and latest research note (up to 3 symbols);
- otherwise a top-10 table by the category named in the question (value, quality, growth, momentum,
  risk, ml) or by total.

Retrieval is rule-based because the Jetson's Qwen2.5-3B has no reliable tool calling; the model only
explains what it is given. Open WebUI's own title/tag requests (`### Task:`) are forwarded untouched.
Rankings skip symbols whose last score is more than 10 days old (delisted ex-members).

Run locally: `uvicorn assistant.app:app --port 8090`. On the Jetson:
`docker compose -f assistant/docker-compose.yml up -d --build` (mounts the lake read-only; host port 8095 because 8090 is taken on the Jetson).
Then in Open WebUI: Admin > Settings > Connections > OpenAI API > add `http://10.0.0.20:8095/v1`
with any API key, and pick `sher-advisor` in the model list.

Not built: comparisons beyond 3 symbols, backtest or intraday questions, conversation memory of
looked-up symbols (a follow-up that omits the ticker gets a ranking instead).
