FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY data/ data/
COPY prompts/ prompts/

ENV PYTHONUNBUFFERED=1 \
    EMBEDDING_CACHE_DIR=/app/.cache/embeddings \
    CACHE_PERSIST_PATH=/app/state/semantic_cache.json

RUN python -c "from backend.services.config_planner import ensure_dense_index; from backend.services.relevance import semantic_relevant; assert ensure_dense_index(); semantic_relevant('warm up')"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
