FROM python:3.12-slim
WORKDIR /app
COPY assistant/requirements.txt assistant/requirements.txt
RUN pip install --no-cache-dir -r assistant/requirements.txt
COPY collector/__init__.py collector/store.py collector/
COPY ai/__init__.py ai/rag.py ai/
COPY quant/__init__.py quant/scoring.py quant/
COPY assistant assistant
ENV STOCK_MARKET_DIR=/data
CMD ["uvicorn", "assistant.app:app", "--host", "0.0.0.0", "--port", "8090"]
