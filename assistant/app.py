"""OpenAI-compatible chat endpoint for Open WebUI: grounds each question in the advisor's own
scores/factors/research notes (assistant.context) and forwards it to the llama.cpp backend.
Open WebUI lists it as the model `sher-advisor` (Admin > Settings > Connections, base URL
http://<host>:8095/v1 on the Jetson, any API key).

Usage:
    uvicorn assistant.app:app --host 0.0.0.0 --port 8090
"""
import os
from pathlib import Path

import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from assistant.context import build_context

LLM_URL = os.environ.get("LLM_BASE_URL", "http://10.0.0.20:8080")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen")
MODEL_ID = "sher-advisor"
SYSTEM = (Path(__file__).parent / "prompts" / "system.md").read_text()
# Open WebUI sends title/tag/follow-up generation through the same model; those need no data.
OPEN_WEBUI_TASK = "### Task:"

app = FastAPI()


class ChatRequest(BaseModel):
    messages: list[dict]
    stream: bool = False
    temperature: float = 0.2
    max_tokens: int | None = None


def grounded_messages(messages: list[dict]) -> list[dict]:
    question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if not isinstance(question, str) or question.startswith(OPEN_WEBUI_TASK):
        return messages
    history = [m for m in messages if m["role"] != "system"]
    return [{"role": "system", "content": SYSTEM.format(context=build_context(question))}, *history]


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "sher-advisor"}]}


@app.post("/v1/chat/completions")
def chat(request: ChatRequest):
    payload = {
        "model": LLM_MODEL, "messages": grounded_messages(request.messages), "stream": request.stream,
        "temperature": request.temperature, **({"max_tokens": request.max_tokens} if request.max_tokens else {}),
    }
    upstream = requests.post(f"{LLM_URL}/v1/chat/completions", json=payload, stream=request.stream, timeout=600)
    if not request.stream:
        return JSONResponse(upstream.json(), status_code=upstream.status_code)
    return StreamingResponse(upstream.iter_content(chunk_size=None), media_type="text/event-stream", status_code=upstream.status_code)
